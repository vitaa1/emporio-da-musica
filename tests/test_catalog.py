"""Catalog rules run offline against synthetic and bundled snapshot records."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from emporio_da_musica.catalog import search_catalog
from emporio_da_musica.contracts.intents import ProductSearch
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.data.records import Category, Product, Promotion, Snapshot


@pytest.fixture
def snapshot():
    products = {
        i: Product(
            i,
            Decimal("10.10"),
            f"Violão Modelo {i}",
            1,
            "",
            2,
            "active",
            {},
            date(2025, 1, 1),
        )
        for i in range(1, 8)
    }
    return Snapshot(
        categories={
            1: Category(1, "Cordas acústicas", ""),
            2: Category(2, "Empty", ""),
        },
        products=products,
        customers={},
        orders={},
        order_items={},
        promotions={},
        promotions_by_product={i: () for i in products},
    )


def search(snapshot, **kwargs):
    return search_catalog(snapshot, ProductSearch(type="product_search", **kwargs))


def test_normalization_order_bound_and_no_matches(snapshot):
    snapshot.products = dict(reversed(list(snapshot.products.items())))
    result = search(snapshot, query="  VIOLA\u0303O  MODELO ", category="ACUSTICAS")
    assert [p.product_id for p in result.data.products] == [1, 2, 3, 4, 5]
    assert result.data.total_matches == 7
    assert search(snapshot, query="missing").status == "not_found"
    assert search(snapshot, category="Empty").status == "not_found"
    assert search(snapshot, query="Modelo 7").data.total_matches == 1


@pytest.mark.parametrize(
    "status,stock,quantity,expected",
    [
        ("active", 2, 2, "available"),
        ("active", 2, 3, "insufficient_stock"),
        ("active", 0, 1, "insufficient_stock"),
        ("discontinued", 20, 1, "discontinued"),
        ("coming_soon", 20, 1, "coming_soon"),
    ],
)
def test_availability(snapshot, status, stock, quantity, expected):
    snapshot.products[1] = replace(
        snapshot.products[1], status=status, stock_quantity=stock
    )
    result = search(snapshot, query="Modelo 1", quantity=quantity)
    assert result.status == "success"
    assert result.data.products[0].availability == expected
    filtered = search(
        snapshot, query="Modelo 1", quantity=quantity, available_only=True
    )
    assert filtered.status == ("success" if expected == "available" else "not_found")


@pytest.mark.parametrize(
    "active,percent,payment,expected",
    [
        (False, "20", "pix", "9.60"),
        (True, "20", "pix", "8.08"),
        (True, "0", "pix", "10.10"),
        (True, "100", "debit", "0.00"),
        (False, "20", "debit", "10.10"),
        (False, "20", None, "10.10"),
    ],
)
def test_discount_precedence(snapshot, active, percent, payment, expected):
    snapshot.promotions_by_product[1] = (Promotion(1, 1, Decimal(percent), "", active),)
    quote = search(snapshot, query="Modelo 1", payment_method=payment).data.products[0]
    assert quote.final_total_brl == Decimal(expected)
    assert quote.promotion_percent == (Decimal(percent) if active else None)
    assert quote.quantity == 1
    assert quote.assumptions


def test_rounding_quantity_budget_and_no_implicit_availability_filter(snapshot):
    result = search(
        snapshot,
        query="Modelo 1",
        payment_method="pix",
        quantity=3,
        max_price_brl="28.80",
    )
    quote = result.data.products[0]
    assert quote.final_total_brl == Decimal("28.80")  # 9.595 -> 9.60, then * 3.
    assert quote.availability == "insufficient_stock"
    assert not quote.assumptions
    assert (
        search(
            snapshot,
            query="Modelo 1",
            payment_method="pix",
            quantity=3,
            max_price_brl="28.79",
        ).status
        == "not_found"
    )
    assert (
        search(
            snapshot,
            query="Modelo 1",
            payment_method="debit",
            quantity=3,
            max_price_brl="28.80",
        ).status
        == "not_found"
    )


@pytest.mark.parametrize(
    "fields,status,reason",
    [
        (
            {"payment_method": "combined"},
            "requires_confirmation",
            "COMBINED_PAYMENT_REQUIRES_CONFIRMATION",
        ),
        ({"installments": 3}, "needs_information", "PAYMENT_METHOD_MISSING"),
        (
            {"payment_method": "pix", "installments": 3},
            "needs_information",
            "INCOMPATIBLE_PAYMENT_CONDITIONS",
        ),
        (
            {"payment_method": "credit", "installments": 3},
            "requires_confirmation",
            "AMBIGUOUS_INSTALLMENT_BAND",
        ),
        (
            {"payment_method": "credit", "installments": 6},
            "unavailable",
            "INSTALLMENT_QUOTE_NOT_SUPPORTED",
        ),
    ],
)
def test_unsupported_payment_is_not_silently_quoted(snapshot, fields, status, reason):
    result = search(snapshot, **fields)
    assert result.status == status
    assert result.reason_code == reason
    assert result.data is None


def test_multiple_active_promotions_require_confirmation(snapshot):
    snapshot.promotions_by_product[1] = tuple(
        Promotion(i, 1, Decimal("10"), "", True) for i in (1, 2)
    )
    assert (
        search(snapshot, query="Modelo 1").reason_code == "MULTIPLE_ACTIVE_PROMOTIONS"
    )


def test_demo_edge_cases():
    snapshot = load_snapshot(Path(__file__).resolve().parents[1] / "data/demo")
    for product in snapshot.products.values():
        result = search(snapshot, query=product.name, payment_method="pix")
        quote = next(
            p for p in result.data.products if p.product_id == product.product_id
        )
        expected = (
            product.status
            if product.status != "active"
            else "available"
            if product.stock_quantity
            else "insufficient_stock"
        )
        assert quote.availability == expected
    for identifier, percent in [(127, "10"), (121, "20"), (90, "18"), (94, "8")]:
        product = snapshot.products[identifier]
        quote = search(
            snapshot, query=product.name, payment_method="pix"
        ).data.products[0]
        assert quote.promotion_percent == Decimal(percent)


@pytest.mark.parametrize("installments", range(1, 13))
def test_credit_installment_band_states(snapshot, installments):
    result = search(
        snapshot, query="Modelo 1", payment_method="credit", installments=installments
    )
    if installments == 1:
        assert result.status == "success"
        assert result.data.products[0].installments == 1
    else:
        assert result.data is None
        assert result.policy_references == ("3.1",)
        if installments <= 3:
            assert result.status == "requires_confirmation"
            assert result.reason_code == "AMBIGUOUS_INSTALLMENT_BAND"
        else:
            assert result.status == "unavailable"
            assert result.reason_code == "INSTALLMENT_QUOTE_NOT_SUPPORTED"
