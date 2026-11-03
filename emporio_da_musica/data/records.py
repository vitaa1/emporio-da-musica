"""Typed snapshot records, independent of CSV parsing and business rules."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Category:
    category_id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    product_id: int
    price_brl: Decimal
    name: str
    category_id: int
    description: str
    stock_quantity: int
    status: str
    specs: dict[str, Any]
    created_at: date


@dataclass(frozen=True, repr=False)
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True, repr=False)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    total_brl: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None


@dataclass(frozen=True)
class OrderItem:
    order_id: int
    quantity: int
    product_id: int


@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool


@dataclass(repr=False)
class Snapshot:
    """Validated records and indexes; callers must enforce session authorization."""

    categories: dict[int, Category]
    products: dict[int, Product]
    customers: dict[int, Customer]
    orders: dict[int, Order]
    order_items: dict[tuple[int, int], OrderItem]
    promotions: dict[int, Promotion]
    products_by_category: dict[int, tuple[Product, ...]] = field(default_factory=dict)
    orders_by_customer: dict[int, tuple[Order, ...]] = field(default_factory=dict)
    items_by_order: dict[int, tuple[OrderItem, ...]] = field(default_factory=dict)
    promotions_by_product: dict[int, tuple[Promotion, ...]] = field(
        default_factory=dict
    )
