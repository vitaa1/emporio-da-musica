"""Offline conversations verify execution, pending facts, and trust boundaries."""

from dataclasses import replace
from decimal import Decimal

import pytest

from emporio_da_musica.providers.base import ProviderError

from .support import payment, search, turn, update


def test_search_then_ordinal_and_corrected_payment(app):
    response = turn(app, search("Violão"))
    assert "1. Violão A" in response.text and "2. Violão B" in response.text
    assert app.session.displayed_product_ids == (10, 20)
    response = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2},
            quantity=2,
            payment_method="pix",
        ),
    )
    assert response.results[-1].data.product_id == 20
    assert "R$ 3.800,00" in response.text
    assert app.session.selected_product_id == 20
    response = turn(
        app,
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="debit"
        ),
    )
    assert response.results[-1].data.final_total_brl == Decimal("2000")


def test_pending_partial_updates_keep_resolved_product(app):
    turn(app, search("Violão"))
    response = turn(app, payment(product_reference={"kind": "ordinal", "ordinal": 2}))
    assert response.results[-1].missing_fields == ("quantity", "payment_method")
    pending_id = app.session.pending[0].pending_id
    update(app, quantity=2)
    assert app.session.pending[0].pending_id == pending_id
    assert app.session.pending[0].records.product_id == 20
    response = update(app, payment_method="pix")
    assert response.results[-1].data.product_id == 20
    assert response.results[-1].data.final_total_brl == Decimal("3800")
    assert not app.session.pending


def test_ambiguous_lookup_waits_while_independent_search_succeeds(app):
    response = turn(
        app,
        search("Violão"),
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
        search("Piano"),
    )
    assert [r.status for r in response.results] == [
        "success",
        "needs_information",
        "success",
    ]
    assert app.session.displayed_product_ids == (10, 20, 30)
    assert response.text.index("Piano") < response.text.index("Para continuar")
    response = update(app, product_reference={"kind": "ordinal", "ordinal": 2})
    assert response.results[-1].data.product_id == 20


def test_selected_dependency_uses_preceding_success_and_clears_stale_selection(app):
    response = turn(
        app,
        search("Piano"),
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
    )
    assert response.results[-1].data.product_id == 30
    response = turn(
        app,
        search("missing"),
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
    )
    assert response.results[-1].status == "needs_information"
    assert app.session.selected_product_id is None


def test_ordinal_cannot_refer_to_predicted_results_in_same_turn(app):
    response = turn(
        app,
        search("Piano"),
        payment(
            product_reference={"kind": "ordinal", "ordinal": 1},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].status == "needs_information"


def test_multiple_lists_use_global_ordinals(app):
    response = turn(app, search("Piano"), search("Violão"))
    assert app.session.displayed_product_ids == (30, 10, 20)
    assert "1. Piano" in response.text and "3. Violão B" in response.text
    response = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 1},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].data.product_id == 30


def test_query_reference_does_not_choose_first_ambiguous_match(app):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Violão"},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].status == "needs_information"
    assert app.session.selected_product_id is None
    response = update(app, product_reference={"kind": "ordinal", "ordinal": 2})
    assert response.results[-1].data.product_id == 20


def test_exact_resolved_id_not_name_research(app):
    app.snapshot.products[20] = replace(app.snapshot.products[20], name="Violão A")
    turn(app, search("Violão A"))
    response = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].data.product_id == 20
    assert response.results[-1].data.final_total_brl == Decimal("1900")


@pytest.mark.parametrize(
    "bad",
    [
        {"intents": [search("Piano"), {"type": "product_search", "price": "0"}]},
        {"intents": [{"type": "order_status", "customer_id": 1}]},
        "invalid json",
    ],
)
def test_invalid_proposals_execute_nothing(app, monkeypatch, bad):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid proposal reached execution")

    monkeypatch.setattr("emporio_da_musica.controller.search_catalog", forbidden)
    app.provider.responses.extend([bad, bad])
    response = app.handle("input")
    assert not response.results
    assert len(app.provider.requests) == 2
    assert app.provider.requests[-1].repair_requested
    assert not app.session.displayed_product_ids


def test_one_repair_can_succeed_and_provider_failure_is_not_retried(app):
    app.provider.responses.extend(["broken", {"intents": [search("Piano")]}])
    assert app.handle("input").results[0].status == "success"
    app.provider.responses.append(ProviderError("secret diagnostic"))
    response = app.handle("input")
    assert not response.results and "secret" not in response.text
    assert len(app.provider.requests) == 3


def test_broad_proposal_is_not_repaired(app):
    response = turn(app, *[search("Piano")] * 6)
    assert not response.results
    assert "cinco" in response.text
    assert len(app.provider.requests) == 1


def test_invalid_clarification_preserves_pending_and_identity(app):
    turn(app, payment(quantity=1))
    old = app.session.pending
    response = update(app, quantity=999)
    assert not response.results
    assert app.session.pending == old
    assert app.session.simulated_customer_id is None
    app.provider.responses.append(
        {"pending_id": "unknown", "update": payment(payment_method="pix")}
    )
    assert not app.handle("input").results
    assert app.session.pending == old


def test_null_update_remains_missing_and_new_turn_replaces_pending(app):
    turn(app, payment())
    update(app, quantity=None)
    assert "quantity" in app.session.pending[0].requested_fields
    turn(app, search("Piano"))
    assert not app.session.pending


def test_cancel_is_local_and_history_is_bounded(app):
    turn(app, payment())
    calls = len(app.provider.requests)
    app.handle("/cancelar")
    assert not app.session.pending and len(app.provider.requests) == calls
    for _ in range(12):
        turn(app, search("Piano"))
    assert len(app.session.history) == 20
    assert app.provider.requests[-1].displayed_product_names == ("Piano",)


@pytest.mark.parametrize("message", ["", "   ", "x" * 4001])
def test_invalid_message_does_not_call_provider(app, message):
    assert not app.handle(message).results
    assert not app.provider.requests
    assert not app.session.history


def test_operation_failure_is_redacted_and_independent_work_continues(
    app, monkeypatch, caplog
):
    from emporio_da_musica.catalog import search_catalog

    def failing(snapshot, intent):
        if intent.query == "bad":
            raise ArithmeticError("sensitive source value")
        return search_catalog(snapshot, intent)

    monkeypatch.setattr("emporio_da_musica.controller.search_catalog", failing)
    response = turn(app, search("bad"), search("Piano"))
    assert [r.status for r in response.results] == ["error", "success"]
    assert "sensitive" not in response.text + caplog.text
    assert response.text.index("Piano") < response.text.index("Não consegui")


def test_unsupported_order_does_not_disclose_existence(app):
    a = turn(app, {"type": "order_status", "order_id": 1})
    b = turn(app, {"type": "order_status", "order_id": 999})
    assert a.text == b.text
    assert a.results[0].status == "unauthorized"


def test_partial_update_does_not_pick_an_unrelated_later_search(app):
    turn(
        app,
        search("Violão"),
        payment(product_reference={"kind": "selected"}),
        search("Piano"),
    )
    response = update(app, quantity=1, payment_method="pix")
    assert response.results[-1].status == "needs_information"
    assert response.results[-1].missing_fields == ("product_reference",)
    assert app.session.pending[0].records.product_id is None
    response = update(app, product_reference={"kind": "ordinal", "ordinal": 2})
    assert response.results[-1].data.product_id == 20


def test_five_pending_operations_and_focused_question(app):
    response = turn(app, *[payment()] * 5)
    assert len(app.session.pending) == 5
    assert response.text.count("Para continuar") == 1
    update(
        app,
        product_reference={"kind": "query", "query": "Piano"},
        quantity=1,
        payment_method="pix",
    )
    assert len(app.session.pending) == 4


def test_large_catalog_output_does_not_overflow_history(app):
    app.snapshot.products[30] = replace(
        app.snapshot.products[30], name="Piano" + "x" * 3995
    )
    response = turn(app, search("Piano"))
    assert len(response.text) > 4000
    assert len(app.session.history[-1].content) <= 4000
    assert response.results[0].data.products[0].product_id == 30


def test_search_payment_correction_is_revalidated(app):
    response = turn(
        app, {"type": "product_search", "query": "Piano", "installments": 1}
    )
    assert response.results[0].status == "needs_information"
    response = update(app, payment_method="pix")
    assert response.results[0].status == "needs_information"
    response = update(app, payment_method="credit", installments=1)
    assert response.results[0].status == "success"
    assert not app.session.pending


def test_failed_reference_does_not_leave_a_stale_selected_product(app):
    turn(app, search("Piano"))
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "missing"},
            quantity=1,
            payment_method="pix",
        ),
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
    )
    assert [r.status for r in response.results] == ["not_found", "needs_information"]
    assert app.session.selected_product_id is None


def test_quote_keeps_selection_when_independent_search_replaces_old_list(app):
    turn(app, search("Violão"))
    response = turn(
        app,
        search("Piano"),
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert app.session.displayed_product_ids == (30, 20)
    assert app.session.selected_product_id == 20
    assert "1. Piano" in response.text
    assert "2. Violão B" in response.text
    response = turn(
        app,
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="debit"
        ),
    )
    assert response.results[-1].status == "success"
    assert response.results[-1].data.product_id == 20
    assert response.results[-1].data.final_total_brl == Decimal("2000")
