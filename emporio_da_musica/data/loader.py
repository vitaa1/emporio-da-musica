"""Load and validate CSV snapshots without applying business policy."""

import csv
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .records import Category, Customer, Order, OrderItem, Product, Promotion, Snapshot


class DataError(ValueError):
    """Invalid source data, reported without exposing source field values."""


def _text(value: str) -> str:
    if not value:
        raise ValueError
    return value


def _integer(value: str, minimum: int = 0) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError
    number = int(value)
    if number < minimum:
        raise ValueError
    return number


def _id(value: str) -> int:
    return _integer(value, 1)


def _decimal(value: str) -> Decimal:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError
    return Decimal(value)


def _money(value: str) -> Decimal:
    amount = _decimal(value)
    if amount.as_tuple().exponent < -2:
        raise ValueError
    return amount


def _percent(value: str) -> Decimal:
    amount = _decimal(value)
    if amount > 100:
        raise ValueError
    return amount


def _date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError
    return date.fromisoformat(value)


def _optional_text(value: str) -> str | None:
    return value or None


def _optional_date(value: str) -> date | None:
    return _date(value) if value else None


def _flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise ValueError
    return value == "1"


def _choice(*choices: str):
    def parse(value: str) -> str:
        if value not in choices:
            raise ValueError
        return value

    return parse


def _payment(value: str) -> str:
    if value not in {"pix", "debit", "boleto"} and not re.fullmatch(
        r"credit_(?:[1-9]|1[0-2])x", value
    ):
        raise ValueError
    return value


def _specs(value: str) -> dict[str, Any]:
    def unique_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    def invalid_constant(value):
        raise ValueError

    result = json.loads(
        value,
        parse_float=Decimal,
        parse_constant=invalid_constant,
        object_pairs_hook=unique_pairs,
    )
    if not isinstance(result, dict):
        raise ValueError
    return result


SCHEMAS = {
    "categories": (Category, {"category_id": _id, "name": _text, "description": _text}),
    "products": (
        Product,
        {
            "product_id": _id,
            "price_brl": _money,
            "name": _text,
            "category_id": _id,
            "description": _text,
            "stock_quantity": _integer,
            "status": _choice("active", "discontinued", "coming_soon"),
            "specs": _specs,
            "created_at": _date,
        },
    ),
    "customers": (
        Customer,
        dict.fromkeys(("customer_id",), _id)
        | dict.fromkeys(("name", "phone", "email", "city"), _text),
    ),
    "orders": (
        Order,
        {
            "order_id": _id,
            "customer_id": _id,
            "order_date": _date,
            "status": _choice(
                "pending", "confirmed", "shipped", "delivered", "cancelled"
            ),
            "total_brl": _money,
            "payment_method": _payment,
            "tracking_code": _optional_text,
            "estimated_delivery": _optional_date,
            "notes": _optional_text,
        },
    ),
    "order_items": (
        OrderItem,
        {"order_id": _id, "quantity": _id, "product_id": _id},
    ),
    "promotions": (
        Promotion,
        {
            "promotion_id": _id,
            "product_id": _id,
            "discount_percent": _percent,
            "description": _text,
            "is_active": _flag,
        },
    ),
}


def _read(directory: Path, table: str):
    model, schema = SCHEMAS[table]
    records = {}
    locations = {}
    path = directory / f"desafio_tecnico_ai_eng - {table}.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, None)
            if (
                header is None
                or len(header) != len(schema)
                or set(header) != set(schema)
            ):
                raise DataError(f"{table}: invalid or missing header")
            for values in reader:
                line = reader.line_num
                if len(values) != len(header):
                    raise DataError(f"{table}: line {line}: invalid column count")
                normalized = {}
                for name, value in zip(header, values, strict=True):
                    try:
                        normalized[name] = schema[name](value.strip())
                    except (ValueError, ArithmeticError, RecursionError):
                        raise DataError(
                            f"{table}: line {line}: invalid {name}"
                        ) from None
                record = model(**normalized)
                key = (
                    (record.order_id, record.product_id)
                    if table == "order_items"
                    else getattr(record, next(iter(schema)))
                )
                if key in records:
                    raise DataError(f"{table}: line {line}: duplicate key")
                records[key] = record
                locations[key] = line
    except (OSError, UnicodeError, csv.Error):
        raise DataError(f"{table}: cannot read valid UTF-8 CSV source") from None
    return records, locations


def _group(records, attribute: str, parent_ids):
    groups = {key: [] for key in parent_ids}
    for record in records.values():
        groups[getattr(record, attribute)].append(record)
    return {key: tuple(values) for key, values in groups.items()}


def load_snapshot(directory: str | Path) -> Snapshot:
    """Load all six tables atomically; raise DataError on the first invalid record."""
    tables = {}
    locations = {}
    for table in SCHEMAS:
        tables[table], locations[table] = _read(Path(directory), table)
    relationships = (
        ("products", "category_id", "categories"),
        ("orders", "customer_id", "customers"),
        ("order_items", "order_id", "orders"),
        ("order_items", "product_id", "products"),
        ("promotions", "product_id", "products"),
    )
    for table, attribute, parent in relationships:
        for key, record in tables[table].items():
            if getattr(record, attribute) not in tables[parent]:
                raise DataError(
                    f"{table}: line {locations[table][key]}: orphan {attribute}"
                )
    snapshot = Snapshot(**tables)
    snapshot.products_by_category = _group(
        snapshot.products, "category_id", snapshot.categories
    )
    snapshot.orders_by_customer = _group(
        snapshot.orders, "customer_id", snapshot.customers
    )
    snapshot.items_by_order = _group(snapshot.order_items, "order_id", snapshot.orders)
    snapshot.promotions_by_product = _group(
        snapshot.promotions, "product_id", snapshot.products
    )
    return snapshot
