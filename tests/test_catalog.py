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


def test_normalization_order_bound_and_no_matches(snapshot, monkeypatch):
    # A smaller bound exercises truncation with the seven-product fixture.
    monkeypatch.setattr("emporio_da_musica.catalog.MAX_CATALOG_RESULTS", 5)
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


def priced(snapshot, price, stock=10):
    product = replace(
        snapshot.products[1], price_brl=Decimal(price), stock_quantity=stock
    )
    return replace(snapshot, products={1: product})


@pytest.mark.parametrize("installments", [2, 3])
def test_ambiguous_installment_band_requires_confirmation(snapshot, installments):
    result = search(
        snapshot, query="Modelo 1", payment_method="credit", installments=installments
    )
    assert result.status == "requires_confirmation"
    assert result.reason_code == "AMBIGUOUS_INSTALLMENT_BAND"
    assert result.policy_references == ("3.1",)
    assert result.data is None


@pytest.mark.parametrize(
    ("price", "count", "eligible"),
    [
        ("320.00", 4, True),  # exactly BRL 80 each
        ("319.99", 4, False),
        ("480.00", 6, True),
        ("479.99", 6, False),
        ("700.00", 7, True),  # exactly BRL 100 each
        ("699.99", 7, False),
        ("1200.00", 12, True),
        ("1199.99", 12, False),
    ],
)
def test_installment_minimum_boundaries(snapshot, price, count, eligible):
    result = search(
        priced(snapshot, price),
        query="Modelo 1",
        payment_method="credit",
        installments=count,
    )
    quote = result.data.products[0]
    assert result.policy_references == ("3", "3.1", "6")
    assert quote.final_total_brl == Decimal(price)
    if eligible:
        assert quote.installments == count
        assert quote.installment_amount_brl * count == Decimal(price)
        assert quote.first_installment_brl is None
    else:
        assert quote.installments is None
        assert quote.installment_amount_brl is None
        assert "Requested installments do not meet the minimum." in quote.assumptions


def test_installment_rounding_puts_remainder_in_first(snapshot):
    quote = search(
        priced(snapshot, "1000.00"),
        query="Modelo 1",
        payment_method="credit",
        installments=7,
    ).data.products[0]
    assert quote.installment_amount_brl == Decimal("142.85")
    assert quote.first_installment_brl == Decimal("142.90")
    assert quote.first_installment_brl + 6 * quote.installment_amount_brl == Decimal(
        "1000.00"
    )


def test_installments_use_quantity_total_and_promotion_without_pix(snapshot):
    snapshot = priced(snapshot, "100.00")
    snapshot.promotions_by_product[1] = (Promotion(1, 1, Decimal("20"), "", True),)
    quote = search(
        snapshot,
        query="Modelo 1",
        quantity=5,
        payment_method="credit",
        installments=5,
    ).data.products[0]
    assert quote.final_total_brl == Decimal("400.00")
    assert quote.installment_amount_brl == Decimal("80.00")


@pytest.mark.parametrize(
    ("price", "maximum"),
    [("10.10", None), ("319.99", None), ("320.00", 4), ("699.99", 6), ("1200", 12)],
)
def test_credit_without_count_reports_maximum(snapshot, price, maximum):
    quote = search(
        priced(snapshot, price), query="Modelo 1", payment_method="credit"
    ).data.products[0]
    assert quote.max_installments == maximum
    assert quote.installments is None


def test_single_credit_installment_is_a_plain_quote(snapshot):
    quote = search(
        snapshot, query="Modelo 1", payment_method="credit", installments=1
    ).data.products[0]
    assert quote.installments == 1
    assert quote.installment_amount_brl is None


def test_default_bound_shows_all_bundled_yamaha_guitars():
    from pathlib import Path

    from emporio_da_musica.data.loader import load_snapshot

    bundled = load_snapshot(Path(__file__).resolve().parents[1] / "data/demo")
    result = search(bundled, query="Yamaha", category="Violões")
    assert result.data.total_matches == 7
    assert len(result.data.products) == 7


def test_wrong_model_category_falls_back_to_name_search():
    from pathlib import Path

    from emporio_da_musica.data.loader import load_snapshot

    bundled = load_snapshot(Path(__file__).resolve().parents[1] / "data/demo")
    result = search(bundled, query="Takamine GD20", category="Guitarras")
    assert result.status == "success"
    assert result.data.products[0].name == "Takamine GD20 Dreadnought Natural"
    assert "one was ignored" in result.data.products[0].assumptions[-1]
    assert search(bundled, query="Inexistente", category="Guitarras").status == (
        "not_found"
    )
    assert search(bundled, category="Sopros").status == "not_found"

    # Another instrument never falls back to a category listing.
    assert search(bundled, query="violino", category="Violões").status == "not_found"


def test_small_installment_note_appears_once_in_listing(snapshot):
    from emporio_da_musica.composer import SMALL_INSTALLMENTS_NOTE, compose

    result = search(snapshot, query="Modelo", payment_method="credit")
    ids = tuple(q.product_id for q in result.data.products)
    text = compose([result], ids, ())
    assert text.count(SMALL_INSTALLMENTS_NOTE) == 1
