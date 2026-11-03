"""Local freight (§5.1): subtotal boundaries, region, and missing facts."""

from dataclasses import replace
from decimal import Decimal

import pytest

from emporio_da_musica.data.records import Promotion

from .support import search, turn, update

CAMPO_GRANDE = {"city": "Campo Grande", "state": "MS"}


def shipping(**fields):
    return {"type": "shipping_quote", **fields}


def named(**fields):
    return shipping(product_reference={"kind": "query", "query": "Piano"}, **fields)


def priced(app, price, stock=3, status="active"):
    product = replace(
        app.snapshot.products[30],
        price_brl=Decimal(price),
        stock_quantity=stock,
        status=status,
    )
    app.snapshot = replace(app.snapshot, products={30: product})
    return app


@pytest.mark.parametrize(
    ("price", "status", "freight"),
    [
        ("499.99", "success", Decimal("35")),
        ("500.00", "requires_confirmation", None),
        ("500.01", "success", Decimal("0.00")),
    ],
)
def test_free_freight_boundary(app, price, status, freight):
    priced(app, price)
    response = turn(
        app,
        named(quantity=1, payment_method="debit", destination=CAMPO_GRANDE),
    )
    result = response.results[-1]
    assert result.status == status
    if freight is None:
        assert result.reason_code == "FREE_FREIGHT_BOUNDARY"
        assert "exatamente R$ 500,00" in response.text
    else:
        assert result.data.freight_brl == freight
        assert result.data.subtotal_brl == Decimal(price)
        assert "1 a 3 dias úteis" in response.text
        assert "não uma data de entrega garantida" in response.text


def test_subtotal_uses_pix_discount_and_quantity(app):
    priced(app, "260.00")
    response = turn(
        app, named(quantity=2, payment_method="pix", destination=CAMPO_GRANDE)
    )
    data = response.results[-1].data
    assert data.subtotal_brl == Decimal("494.00")  # 2 × 247.00 after 5% PIX
    assert data.freight_brl == Decimal("35")
    assert "total com frete: R$ 529,00" in response.text


def test_subtotal_uses_promotion_without_pix(app):
    priced(app, "600.00")
    app.snapshot.promotions_by_product[30] = (
        Promotion(1, 30, Decimal("20"), "", True),
    )
    response = turn(
        app, named(quantity=1, payment_method="pix", destination=CAMPO_GRANDE)
    )
    assert response.results[-1].data.subtotal_brl == Decimal("480.00")
    assert response.results[-1].data.freight_brl == Decimal("35")


def test_missing_facts_are_requested_not_defaulted(app):
    priced(app, "300.00")
    response = turn(app, named())
    result = response.results[-1]
    assert result.status == "needs_information"
    assert result.missing_fields == ("quantity", "payment_method", "destination")
    response = update(
        app, quantity=1, payment_method="boleto", destination=CAMPO_GRANDE
    )
    assert response.results[-1].data.freight_brl == Decimal("35")


def test_postal_code_alone_does_not_establish_region(app):
    priced(app, "300.00")
    response = turn(
        app,
        named(
            quantity=1,
            payment_method="debit",
            destination={"postal_code": "79002-000"},
        ),
    )
    assert response.results[-1].missing_fields == ("destination",)


@pytest.mark.parametrize(
    "destination",
    [
        {"city": "Dourados", "state": "MS"},
        {"city": "Campo Grande", "state": "RJ"},
        {"city": "São Paulo"},
    ],
)
def test_other_destinations_require_confirmation(app, destination):
    priced(app, "300.00")
    response = turn(
        app, named(quantity=1, payment_method="debit", destination=destination)
    )
    result = response.results[-1]
    assert result.status == "requires_confirmation"
    assert result.reason_code == "DELIVERY_REGION_UNCONFIRMED"
    assert "PAC 5 a 12" in response.text
    assert "R$ 35" not in response.text


def test_city_without_state_is_labeled_assumption(app):
    priced(app, "300.00")
    response = turn(
        app,
        named(
            quantity=1,
            payment_method="debit",
            destination={"city": "campo grande"},
        ),
    )
    assert "Considerei Campo Grande/MS" in response.text


@pytest.mark.parametrize(
    ("stock", "status"), [(0, "active"), (5, "discontinued"), (2, "coming_soon")]
)
def test_unavailable_product_gets_no_freight(app, stock, status):
    priced(app, "300.00", stock=stock, status=status)
    response = turn(
        app, named(quantity=1, payment_method="debit", destination=CAMPO_GRANDE)
    )
    assert response.results[-1].reason_code == "PRODUCT_NOT_SHIPPABLE"


def test_combined_payment_still_requires_confirmation(app):
    priced(app, "3000.00")
    response = turn(
        app,
        named(quantity=1, payment_method="combined", destination=CAMPO_GRANDE),
    )
    assert response.results[-1].reason_code == "COMBINED_PAYMENT_REQUIRES_CONFIRMATION"


def test_shipping_with_installments_shows_both(app):
    priced(app, "1200.00")
    response = turn(
        app,
        named(
            quantity=1,
            payment_method="credit",
            installments=12,
            destination=CAMPO_GRANDE,
        ),
    )
    assert "12x de R$ 100,00" in response.text
    assert "frete grátis" in response.text


def test_selected_product_and_destination_carry_over(app):
    priced(app, "300.00")
    turn(app, search("Piano"))
    turn(app, shipping(product_reference={"kind": "selected"}, quantity=1))
    response = turn(
        app,
        shipping(
            product_reference={"kind": "selected"},
            payment_method="pix",
            destination=CAMPO_GRANDE,
        ),
    )
    assert response.results[-1].data.subtotal_brl == Decimal("285.00")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"product_reference": {"kind": "query", "query": "zzz"}}, "NO_CATALOG_MATCH"),
        ({"quantity": 9}, "PRODUCT_NOT_SHIPPABLE"),
        (
            {"payment_method": "credit", "installments": 3},
            "AMBIGUOUS_INSTALLMENT_BAND",
        ),
    ],
)
def test_failed_quote_is_reported_before_asking_destination(app, fields, reason):
    priced(app, "300.00")
    intent = named(quantity=1, payment_method="pix") | fields
    response = turn(app, intent)
    assert response.results[-1].reason_code == reason
    assert app.session.pending == ()
    assert "cidade" not in response.text


def test_unavailable_product_outside_region_reports_availability(app):
    priced(app, "300.00", stock=0)
    response = turn(
        app,
        named(quantity=1, payment_method="pix", destination={"city": "Dourados"}),
    )
    assert response.results[-1].reason_code == "PRODUCT_NOT_SHIPPABLE"


def test_payment_facts_carry_into_shipping_turn(app):
    priced(app, "300.00")
    turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "query", "query": "Piano"},
            "quantity": 1,
        },
    )
    response = turn(
        app,
        shipping(
            product_reference={"kind": "selected"},
            payment_method="pix",
            destination=CAMPO_GRANDE,
        ),
    )
    assert response.results[-1].data.subtotal_brl == Decimal("285.00")


def test_shipping_destination_never_moves_into_payment(app):
    priced(app, "300.00")
    turn(app, named(quantity=1, destination=CAMPO_GRANDE))
    response = turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "selected"},
            "payment_method": "pix",
        },
    )
    assert response.results[-1].status == "success"
    assert "Entrega" not in response.text


@pytest.mark.parametrize(
    ("postal_code", "status"),
    [("59680-000", "requires_confirmation"), ("79002-000", "success")],
)
def test_postal_code_outside_ms_contradicts_assumed_state(app, postal_code, status):
    priced(app, "300.00")
    response = turn(
        app,
        named(
            quantity=1,
            payment_method="pix",
            destination={"city": "Campo Grande", "postal_code": postal_code},
        ),
    )
    assert response.results[-1].status == status


def completed_pix_quote(app):
    priced(app, "300.00")
    response = turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "query", "query": "Piano"},
            "quantity": 1,
            "payment_method": "pix",
        },
    )
    assert response.results[-1].status == "success"
    assert app.session.pending == ()


def test_completed_quote_facts_carry_into_shipping(app):
    completed_pix_quote(app)
    response = turn(
        app,
        shipping(product_reference={"kind": "selected"}, destination=CAMPO_GRANDE),
        message="E qual o frete dele para Campo Grande/MS?",
    )
    assert response.results[-1].data.subtotal_brl == Decimal("285.00")


def test_completed_quote_quantity_correction_keeps_payment(app):
    completed_pix_quote(app)
    response = turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "selected"},
            "quantity": 2,
        },
    )
    assert response.results[-1].data.final_total_brl == Decimal("570.00")


def test_completed_quote_facts_do_not_move_to_another_product(app):
    completed_pix_quote(app)
    app.snapshot.products[40] = replace(
        app.snapshot.products[30], product_id=40, name="Teclado"
    )
    app.snapshot.promotions_by_product[40] = ()
    turn(app, search("Teclado"))
    response = turn(
        app,
        shipping(product_reference={"kind": "selected"}, destination=CAMPO_GRANDE),
    )
    assert response.results[-1].missing_fields == ("quantity", "payment_method")


def selected_shipping(app):
    return turn(
        app,
        shipping(product_reference={"kind": "selected"}, destination=CAMPO_GRANDE),
    )


def test_reused_quote_facts_are_announced(app):
    completed_pix_quote(app)
    response = selected_shipping(app)
    assert "cotação anterior deste produto" in response.text


def test_cancel_forgets_completed_quote(app):
    completed_pix_quote(app)
    app.handle("/cancelar")
    response = selected_shipping(app)
    assert response.results[-1].missing_fields == ("quantity", "payment_method")


def test_new_search_forgets_completed_quote(app):
    completed_pix_quote(app)
    turn(app, search("Piano"))
    response = selected_shipping(app)
    assert response.results[-1].missing_fields == ("quantity", "payment_method")


def test_failed_quote_forgets_earlier_success(app):
    completed_pix_quote(app)
    turn(
        app,
        shipping(
            product_reference={"kind": "selected"},
            quantity=99,
            destination=CAMPO_GRANDE,
        ),
    )
    response = selected_shipping(app)
    assert "payment_method" in response.results[-1].missing_fields
    assert "R$ 285,00" not in response.text


def test_unavailable_quote_is_not_remembered(app):
    priced(app, "300.00")
    turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "query", "query": "Piano"},
            "quantity": 9,
            "payment_method": "pix",
        },
    )
    response = selected_shipping(app)
    assert response.results[-1].missing_fields == ("quantity", "payment_method")
