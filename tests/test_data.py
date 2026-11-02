"""Synthetic fixtures exercise the loader without disclosing customer data."""

import csv
import subprocess
import sys
from datetime import date
from decimal import Decimal

import pytest

from emporio_da_musica.data.loader import DataError, load_snapshot


@pytest.fixture
def source(tmp_path):
    tables = {
        "categories": [
            {"category_id": "1", "name": "Guitars", "description": "Instruments"},
            {"category_id": "2", "name": "Empty", "description": "No products"},
        ],
        "products": [
            {
                "product_id": "10",
                "price_brl": "520.00",
                "name": "Synthetic guitar",
                "category_id": "1",
                "description": "Example",
                "stock_quantity": "13",
                "status": "discontinued",
                "specs": '{"color":"blue","scale":1.5}',
                "created_at": "2025-01-01",
            }
        ],
        "customers": [
            {
                "customer_id": "20",
                "name": "Synthetic customer",
                "phone": "000000000",
                "email": "example@example.invalid",
                "city": "Example city",
            }
        ],
        "orders": [
            {
                "order_id": "30",
                "customer_id": "20",
                "order_date": "2025-02-01",
                "status": "delivered",
                "total_brl": "499.99",
                "payment_method": "credit_3x",
                "tracking_code": "",
                "estimated_delivery": "",
                "notes": "",
            }
        ],
        "order_items": [{"order_id": "30", "quantity": "2", "product_id": "10"}],
        "promotions": [
            {
                "promotion_id": "40",
                "product_id": "10",
                "discount_percent": "8",
                "description": "Example promotion",
                "is_active": "0",
            }
        ],
    }

    def write():
        for table, rows in tables.items():
            with (tmp_path / f"desafio_tecnico_ai_eng - {table}.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return tmp_path

    return tables, write


def test_normalization_indexes_and_historical_facts(source):
    _, write = source
    directory = write()
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    snapshot = load_snapshot(directory)
    product = snapshot.products[10]
    assert product.price_brl == Decimal("520.00")
    assert product.created_at == date(2025, 1, 1)
    assert product.specs == {"color": "blue", "scale": Decimal("1.5")}
    assert (product.status, product.stock_quantity) == ("discontinued", 13)
    assert snapshot.products_by_category[1] == (product,)
    assert snapshot.products_by_category[2] == ()
    order = snapshot.orders[30]
    assert order.total_brl == Decimal("499.99")
    assert order.payment_method == "credit_3x"
    assert (order.tracking_code, order.estimated_delivery, order.notes) == (None,) * 3
    assert snapshot.orders_by_customer[20] == (order,)
    assert snapshot.items_by_order[30][0].quantity == 2
    assert snapshot.promotions_by_product[10][0].is_active is False
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize(
    "table",
    ["categories", "products", "customers", "orders", "order_items", "promotions"],
)
def test_duplicate_keys(source, table):
    tables, write = source
    tables[table].append(tables[table][0].copy())
    with pytest.raises(DataError, match=rf"{table}: line \d+: duplicate key"):
        load_snapshot(write())


@pytest.mark.parametrize(
    "table,field",
    [
        ("products", "category_id"),
        ("orders", "customer_id"),
        ("order_items", "order_id"),
        ("order_items", "product_id"),
        ("promotions", "product_id"),
    ],
)
def test_orphan_references(source, table, field):
    tables, write = source
    tables[table][0][field] = "999"
    with pytest.raises(DataError, match=f"orphan {field}"):
        load_snapshot(write())


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("products", "price_brl", "NaN"),
        ("products", "price_brl", "Infinity"),
        ("products", "price_brl", "-1"),
        ("products", "price_brl", "1.001"),
        ("products", "stock_quantity", "1.5"),
        ("products", "stock_quantity", "-1"),
        ("products", "product_id", "0"),
        ("products", "status", "unknown"),
        ("products", "created_at", "2025-02-30"),
        ("products", "created_at", "20250101"),
        ("products", "specs", "[]"),
        ("products", "specs", '{"x":NaN}'),
        ("products", "specs", '{"x":1,"x":2}'),
        ("products", "specs", "{"),
        ("customers", "email", " "),
        ("orders", "status", "unknown"),
        ("orders", "payment_method", "credit_13x"),
        ("orders", "estimated_delivery", "unknown"),
        ("order_items", "quantity", "0"),
        ("promotions", "discount_percent", "101"),
        ("promotions", "is_active", "true"),
    ],
)
def test_invalid_values_are_sanitized(source, table, field, value):
    tables, write = source
    tables[table][0][field] = value
    with pytest.raises(DataError) as caught:
        load_snapshot(write())
    assert str(caught.value) == f"{table}: line 2: invalid {field}"
    assert caught.value.__suppress_context__


def test_optional_values_and_active_flag(source):
    tables, write = source
    tables["orders"][0].update(
        tracking_code=" TEST123 ", estimated_delivery="2025-02-10", notes=" Example "
    )
    tables["promotions"][0]["is_active"] = "1"
    snapshot = load_snapshot(write())
    assert snapshot.orders[30].estimated_delivery == date(2025, 2, 10)
    assert snapshot.orders[30].tracking_code == "TEST123"
    assert snapshot.orders[30].notes == "Example"
    assert snapshot.promotions[40].is_active is True


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"category_id,name,name\n1,a,b\n",
        b"category_id,name,description\n1,a,b,extra\n",
        b"category_id,name,description\n1,a\n",
        b'category_id,name,description\n1,a,"unterminated',
        b"category_id,name,description\n1,a,\xff\n",
    ],
)
def test_bad_csv_structure(source, content):
    _, write = source
    directory = write()
    (directory / "desafio_tecnico_ai_eng - categories.csv").write_bytes(content)
    with pytest.raises(DataError):
        load_snapshot(directory)


def test_missing_file(tmp_path):
    with pytest.raises(DataError, match="categories: cannot read"):
        load_snapshot(tmp_path)


def test_reordered_columns_and_zero_values(source):
    tables, write = source
    tables["products"][0].update(price_brl="0", stock_quantity="0")
    tables["promotions"][0]["discount_percent"] = "0"
    tables["products"][0] = dict(reversed(tables["products"][0].items()))
    snapshot = load_snapshot(write())
    assert snapshot.products[10].price_brl == Decimal("0")
    assert snapshot.products[10].stock_quantity == 0
    assert snapshot.promotions[40].discount_percent == Decimal("0")


def test_validation_command_prints_counts_only(source):
    _, write = source
    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica", str(write())],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "categories: 2",
        "products: 1",
        "customers: 1",
        "orders: 1",
        "order_items: 1",
        "promotions: 1",
    ]


def test_validation_command_reports_sanitized_error(source):
    tables, write = source
    tables["orders"][0]["payment_method"] = "private-unexpected-value"
    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica", str(write())],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Data validation failed: orders: line 2: invalid payment_method\n"
    )
