"""Shared synthetic catalog controller fixture."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.records import Category, Product, Snapshot

from .support import FakeProvider


@pytest.fixture
def app():
    products = {
        i: Product(
            i, Decimal("100.00") * i, name, 1, "", 3, "active", {}, date(2025, 1, 1)
        )
        for i, name in [(10, "Violão A"), (20, "Violão B"), (30, "Piano")]
    }
    snapshot = Snapshot(
        categories={1: Category(1, "Instrumentos", "")},
        products=products,
        customers={},
        orders={},
        order_items={},
        promotions={},
        promotions_by_product={i: () for i in products},
    )
    return Controller(
        snapshot,
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
