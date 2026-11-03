"""Return assessments: required facts, injected-clock boundaries, and provenance."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.records import Customer, Order

from .support import FakeProvider, turn, update

GOOD = {
    "original_packaging": True,
    "signs_of_use": False,
    "complete_accessories_manuals": True,
}
# 2026-11-09 03:30 UTC is still 2026-11-08 in Campo Grande (UTC-4).
LATE_EVENING = datetime(2026, 11, 9, 3, 30, tzinfo=timezone.utc)
AFTER_MIDNIGHT = datetime(2026, 11, 9, 4, 30, tzinfo=timezone.utc)


def order(order_id, customer_id, status, ordered, estimate=None):
    return Order(
        order_id,
        customer_id,
        ordered,
        status,
        Decimal("500"),
        "pix",
        None,
        estimate,
        None,
    )


@pytest.fixture
def snapshot(app):
    orders = {
        1: order(1, 1, "delivered", date(2026, 10, 10), date(2026, 11, 7)),
        2: order(2, 1, "delivered", date(2026, 10, 9)),
        3: order(3, 2, "delivered", date(2026, 10, 20)),
        4: order(4, 1, "confirmed", date(2026, 11, 1)),
    }
    return replace(
        app.snapshot,
        customers={
            1: Customer(1, "Synthetic One", "0", "one@example.test", "City"),
            2: Customer(2, "Synthetic Two", "0", "two@example.test", "City"),
        },
        orders=orders,
        orders_by_customer={1: (orders[1], orders[2], orders[4]), 2: (orders[3],)},
    )


def make(snapshot, customer_id=1, now=LATE_EVENING):
    return Controller(
        snapshot, FakeProvider(), clock=lambda: now, customer_id=customer_id
    )


def ret(**fields):
    return {"type": "return_assessment", **fields}


def states(response):
    data = response.results[-1].data
    return data.assessment, {c.name: (c.state, c.provenance) for c in data.conditions}


def test_missing_reason_asks_only_for_reason(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(app, ret(), message="Posso devolver um produto?")
    result = response.results[0]
    assert result.status == "needs_information"
    assert result.missing_fields == ("reason",)
    assert "pedido" not in response.text.split("informe")[-1]
    assert "arrependimento" in response.text


def test_assignment_withdrawal_example_asks_for_required_facts(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(reason="withdrawal"),
        message="Me arrependi da minha compra, posso devolver meu pedido?",
    )
    result = response.results[0]
    assert result.status == "needs_information"
    assert result.missing_fields == ("purchase_channel", "received_at", "condition")
    assert result.policy_references == ("4.1",)
    assert "online ou na loja física" in response.text
    assert "indisponível" not in response.text


@pytest.mark.parametrize(
    ("now", "expected", "window"),
    [
        (LATE_EVENING, "conditions_met", "satisfied"),
        (AFTER_MIDNIGHT, "conditions_not_met", "not_satisfied"),
    ],
)
def test_withdrawal_seven_day_boundary_uses_store_date(snapshot, now, expected, window):
    app = make(snapshot, customer_id=None, now=now)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            purchase_channel="online",
            received_at="2026-11-01",
            condition=GOOD,
        ),
        message="Comprei online, recebi em 01/11 e está tudo intacto.",
    )
    assessment, conditions = states(response)
    assert assessment == expected
    assert conditions["within_7_days_of_receipt"] == (window, "customer_declaration")
    assert "nenhuma devolução, troca ou reembolso foi solicitado" in response.text
    assert "seção 4.1" in response.text


def test_in_store_withdrawal_needs_no_other_facts(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(reason="withdrawal", purchase_channel="in_store"),
        message="Comprei na loja e me arrependi",
    )
    assessment, conditions = states(response)
    assert assessment == "conditions_not_met"
    assert conditions == {"online_purchase": ("not_satisfied", "customer_declaration")}
    assert "troca por defeito ou por preferência" in response.text
    assert app.session.pending == ()


def test_receipt_date_not_typed_in_message_is_discarded(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(reason="withdrawal", purchase_channel="online", received_at="2026-11-05"),
        message="Comprei online e me arrependi",
    )
    assert response.results[0].missing_fields == ("received_at", "condition")


def test_relative_receipt_word_is_accepted(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            purchase_channel="online",
            received_at="yesterday",
            condition=GOOD,
        ),
        message="Comprei online, recebi ontem, tudo lacrado",
    )
    assert states(response)[0] == "conditions_met"


def test_future_receipt_date_is_rejected(snapshot):
    app = make(snapshot, customer_id=None)
    app.provider.responses.extend(
        [{"intents": [ret(reason="withdrawal", received_at="2026-12-01")]}] * 2
    )
    response = app.handle("Recebi em 01/12")
    assert response.results == ()
    assert "Não consegui interpretar" in response.text


def test_delivery_estimate_never_substitutes_for_receipt(snapshot):
    app = make(snapshot)
    response = turn(
        app,
        ret(reason="withdrawal", order_id=1, purchase_channel="online", condition=GOOD),
        message="Quero devolver o pedido 1, comprei online",
    )
    assert response.results[0].missing_fields == ("received_at",)


def test_withdrawal_with_order_checks_record(snapshot):
    app = make(snapshot)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            order_id=4,
            purchase_channel="online",
            received_at="2026-11-02",
            condition=GOOD,
        ),
        message="Pedido 4, comprei online, recebi em 2026-11-02",
    )
    assessment, conditions = states(response)
    assert assessment == "requires_review"
    assert conditions["order_delivered"] == ("requires_review", "system_record")


def test_partial_condition_leaves_unknown_facts(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            purchase_channel="online",
            received_at="today",
            condition={"original_packaging": True},
        ),
        message="Comprei online, recebi hoje, está na caixa",
    )
    assessment, conditions = states(response)
    assert assessment == "requires_review"
    assert conditions["no_signs_of_use"] == ("unknown", "unknown")
    assert "não informada" in response.text


def test_customer_declared_signs_of_use_fail_withdrawal(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            purchase_channel="online",
            received_at="today",
            condition=GOOD | {"signs_of_use": True},
        ),
        message="Comprei online, recebi hoje, já usei",
    )
    assessment, conditions = states(response)
    assert assessment == "conditions_not_met"
    assert conditions["no_signs_of_use"] == ("not_satisfied", "customer_declaration")
    assert "reembolso é feito" not in response.text


def test_defect_requires_order_and_session_identity(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(app, ret(reason="defect"), message="Chegou com defeito")
    assert response.results[0].missing_fields == ("order_id",)
    response = update(app, message="Pedido 1", order_id=1)
    assert response.results[0].status == "unauthorized"
    assert "nenhum pedido foi consultado" in response.text


@pytest.mark.parametrize("order_id", [1, 2])  # days 29 and 30 on 2026-11-08
def test_defect_within_thirty_days_still_needs_inspection(snapshot, order_id):
    app = make(snapshot)
    response = turn(
        app, ret(reason="defect", order_id=order_id), message=f"Pedido {order_id}"
    )
    assessment, conditions = states(response)
    assert assessment == "requires_review"
    assert conditions["within_30_days_of_purchase"] == ("satisfied", "system_record")
    assert conditions["manufacturing_defect"] == (
        "requires_review",
        "customer_declaration",
    )


def test_defect_after_thirty_days_points_to_manufacturer(snapshot):
    app = make(snapshot, now=AFTER_MIDNIGHT)  # 2026-11-09 is day 31 for order 2
    response = turn(app, ret(reason="defect", order_id=2), message="Pedido 2")
    assessment, conditions = states(response)
    assert assessment == "conditions_not_met"
    assert conditions["within_30_days_of_purchase"][0] == "not_satisfied"
    assert "garantia do fabricante" in response.text
    assert response.results[0].policy_references == ("4.2", "4.4", "8.2")


def test_foreign_and_missing_orders_are_indistinguishable(snapshot):
    app = make(snapshot)
    foreign = turn(app, ret(reason="defect", order_id=3), message="Pedido 3")
    missing = turn(app, ret(reason="defect", order_id=99), message="Pedido 99")
    assert foreign.text == missing.text
    assert foreign.results[0].status == "not_found"


def test_defect_reuses_order_in_focus(snapshot):
    app = make(snapshot)
    turn(app, {"type": "order_status", "order_id": 1}, message="Pedido 1")
    response = turn(app, ret(reason="defect"), message="Veio com defeito")
    assert states(response)[0] == "requires_review"


def test_order_number_copied_from_history_is_discarded(snapshot):
    app = make(snapshot)
    response = turn(app, ret(reason="defect", order_id=1), message="Veio com defeito")
    assert response.results[0].missing_fields == ("order_id",)


def test_preference_start_event_always_requires_review(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(app, ret(reason="preference"), message="Quero trocar a cor")
    assert response.results[0].missing_fields == ("condition",)
    response = update(
        app,
        message="Está perfeito, na caixa",
        condition=GOOD | {"customized": False, "final_sale_notice": False},
    )
    assessment, conditions = states(response)
    assert assessment == "requires_review"
    assert conditions["preference_window"] == ("requires_review", "policy")
    assert conditions["desired_product_available"] == ("unknown", "unknown")
    assert "seção 4.3, 4.4" in response.text


def test_customized_item_is_excluded_from_preference_exchange(snapshot):
    app = make(snapshot, customer_id=None)
    response = turn(
        app,
        ret(reason="preference", condition=GOOD | {"customized": True}),
        message="Quero trocar, mas fiz regulagem especial",
    )
    assert states(response)[0] == "conditions_not_met"


def test_clarification_with_extra_facts_is_merged(snapshot):
    app = make(snapshot, customer_id=None)
    turn(app, ret(), message="Quero devolver")
    response = update(
        app,
        message="Me arrependi, comprei online e recebi ontem",
        reason="withdrawal",
        purchase_channel="online",
        received_at="yesterday",
    )
    assert response.results[0].missing_fields == ("condition",)
    response = update(app, message="Tudo intacto e completo", condition=GOOD)
    assert states(response)[0] == "conditions_met"


def test_new_turn_answer_keeps_pending_return_facts(snapshot):
    app = make(snapshot, customer_id=None)
    turn(
        app,
        ret(reason="withdrawal", purchase_channel="online"),
        message="Comprei online e me arrependi",
    )
    response = turn(
        app,
        ret(received_at="2026-11-05", condition=GOOD),
        message="Recebi em 05/11, está tudo na caixa",
    )
    assert states(response)[0] == "conditions_met"


def test_typed_day_is_not_an_order_number(snapshot):
    app = make(snapshot)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            order_id=5,
            purchase_channel="online",
            received_at="2026-11-05",
            condition=GOOD,
        ),
        message="Comprei online, recebi dia 5, tudo intacto",
    )
    assert states(response)[0] == "conditions_met"


def test_unrelated_digit_does_not_keep_invented_receipt(snapshot):
    app = make(snapshot)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            order_id=1,
            purchase_channel="online",
            received_at="2026-10-02",
            condition=GOOD,
        ),
        message="Pedido 1, comprei online, tudo intacto",
    )
    assert response.results[0].missing_fields == ("received_at",)


def test_receipt_before_order_date_puts_window_under_review(snapshot):
    app = make(snapshot)
    response = turn(
        app,
        ret(
            reason="withdrawal",
            order_id=4,
            purchase_channel="online",
            received_at="2026-10-30",
            condition=GOOD,
        ),
        message="Pedido 4, online, recebi em 30/10",
    )
    assessment, conditions = states(response)
    assert assessment == "requires_review"
    assert conditions["within_7_days_of_receipt"][0] == "requires_review"
    assert conditions["receipt_after_order"][0] == "requires_review"


def test_pending_facts_do_not_transfer_to_another_order(snapshot):
    app = make(snapshot)
    turn(
        app,
        ret(reason="withdrawal", order_id=1, purchase_channel="online", condition=GOOD),
        message="Pedido 1, comprei online, tudo intacto",
    )
    response = turn(app, ret(order_id=2), message="E o pedido 2?")
    assert response.results[0].missing_fields == ("reason",)


def test_return_fallback_keeps_other_pending_operations(snapshot):
    app = make(snapshot)
    turn(
        app,
        {
            "type": "payment_options",
            "product_reference": {"kind": "query", "query": "Piano"},
        },
        ret(reason="withdrawal"),
        message="Quanto fica o Piano? E quero devolver uma compra",
    )
    assert len(app.session.pending) == 2
    pending = app.session.pending[1]
    app.provider.responses.append(
        {
            "pending_id": pending.pending_id,
            "update": {
                "type": "return_assessment",
                "purchase_channel": "online",
                "received_at": "yesterday",
                "condition": GOOD,
                "order_id": None,
                "reason": "withdrawal",
            },
        }
    )
    response = app.handle("Online, recebi ontem, tudo intacto")
    assert states(response)[0] == "conditions_met"
    assert [p.declarations.intent.type for p in app.session.pending] == [
        "payment_options"
    ]


def test_carried_facts_that_fail_validation_do_not_raise(snapshot):
    now = [LATE_EVENING]
    app = Controller(snapshot, FakeProvider(), clock=lambda: now[0], customer_id=1)
    turn(app, ret(reason="withdrawal", received_at="today"), message="Recebi hoje")
    now[0] = datetime(2026, 11, 1, tzinfo=timezone.utc)
    response = turn(
        app, ret(reason="withdrawal", purchase_channel="online"), message="Online"
    )
    assert "received_at" in response.results[0].missing_fields
