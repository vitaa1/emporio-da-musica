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


def test_order_without_identity_does_not_disclose_existence(app):
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


def test_new_quote_for_pending_product_keeps_declared_quantity(app):
    turn(app, search("Violão"))
    response = turn(
        app, payment(product_reference={"kind": "ordinal", "ordinal": 2}, quantity=1)
    )
    assert response.results[-1].missing_fields == ("payment_method",)
    # The model answers the clarification with a new turn instead of an update.
    response = turn(
        app, payment(product_reference={"kind": "selected"}, payment_method="pix")
    )
    assert response.results[-1].status == "success"
    assert response.results[-1].data.product_id == 20
    assert response.results[-1].data.quantity == 1
    assert not app.session.pending


def test_quote_for_another_product_does_not_inherit_pending_facts(app):
    turn(app, search("Violão"))
    turn(app, payment(product_reference={"kind": "ordinal", "ordinal": 2}, quantity=3))
    response = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 1}, payment_method="pix"
        ),
    )
    assert response.results[-1].missing_fields == ("quantity",)


def test_search_in_same_turn_blocks_inheriting_other_product_facts(app):
    turn(app, search("Violão"))
    turn(app, payment(product_reference={"kind": "ordinal", "ordinal": 2}, quantity=2))
    response = turn(
        app,
        search("Piano"),
        payment(product_reference={"kind": "selected"}, payment_method="pix"),
    )
    assert response.results[-1].status == "needs_information"
    assert response.results[-1].missing_fields == ("quantity",)


def test_new_installments_are_not_replaced_by_inherited_method(app):
    turn(app, search("Violão"))
    turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2}, payment_method="pix"
        ),
    )
    response = turn(app, payment(installments=1, quantity=1))
    assert response.results[-1].status != "success"
    assert "PIX" not in response.text


def test_budget_not_typed_in_current_message_is_ignored(app):
    budget = {"type": "product_search", "query": "Piano", "max_price_brl": "100"}
    response = turn(app, budget, message="Quanto custa o piano?")
    assert response.results[0].status == "success"
    response = turn(app, budget, message="piano até R$ 100,00")
    assert response.results[0].status == "not_found"
    response = turn(app, {**budget, "max_price_brl": "5000"}, message="até R$5.000")
    assert response.results[0].status == "success"


@pytest.mark.parametrize(
    "message,budget",
    [
        ("piano até R$ 5.000,00", "5000"),
        ("piano até 5000.00", "5000"),
        ("piano até 5 mil", "5000"),
        ("piano até mil e quinhentos", "1000"),
        ("piano até 4.999,90", "4999.90"),
    ],
)
def test_typed_budget_formats_are_kept(app, message, budget):
    intent = {"type": "product_search", "query": "Piano", "max_price_brl": budget}
    response = turn(app, intent, message=message)
    assert "limite de preço não foi reconhecido" not in response.text


def test_dropped_budget_is_announced(app):
    intent = {"type": "product_search", "query": "Piano", "max_price_brl": "100"}
    response = turn(app, intent, message="quanto custa o piano?")
    assert response.results[0].status == "success"
    assert "limite de preço não foi reconhecido" in response.text


def test_model_invented_query_is_dropped_but_typed_query_kept(app):
    intent = {"type": "product_search", "query": "viola", "category": "Instrumentos"}
    response = turn(app, intent, message="quais instrumentos vocês têm?")
    assert response.results[0].data.total_matches == 3
    intent = {"type": "product_search", "query": "violino", "category": "Instrumentos"}
    response = turn(app, intent, message="tem violino?")
    assert response.results[0].status == "not_found"


def test_unique_name_quote_is_shown_once(app):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Piano"},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.text.count("Piano") == 1
    assert "pagamento não informado" not in response.text


def test_ambiguous_name_quote_still_lists_choices(app):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Violão"},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert "Violão A" in response.text and "Violão B" in response.text
    assert response.results[-1].missing_fields == ("product_reference",)


def test_quoting_a_list_item_keeps_the_list_for_later_ordinals(app):
    turn(app, search("Violão"))
    first = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 1},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert app.session.displayed_product_ids == (10, 20)
    assert first.text.startswith("1. Violão A")
    response = turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].data.name == "Violão B"
    assert response.text.startswith("2. Violão B")


def test_new_search_still_replaces_the_list(app):
    turn(app, search("Violão"))
    turn(app, search("Piano"))
    assert app.session.displayed_product_ids == (30,)


def test_quote_without_product_keeps_selection_after_cancel(app):
    turn(app, search("Piano"))
    app.handle("/cancelar")
    response = turn(app, payment(quantity=1))
    assert response.results[-1].missing_fields == (
        "product_reference",
        "payment_method",
    )
    assert app.session.selected_product_id == 30
    response = turn(
        app,
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
    )
    assert response.results[-1].data.name == "Piano"


def test_unresolved_reference_still_drops_selection(app):
    turn(app, search("Piano"))
    turn(app, payment(product_reference={"kind": "ordinal", "ordinal": 9}))
    assert app.session.selected_product_id is None


@pytest.mark.parametrize("query", ["débito", "no cartão", "PIX", "à vista"])
def test_payment_word_is_not_a_product_reference(app, query):
    turn(app, search("Piano"))
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": query},
            quantity=1,
            payment_method="debit",
        ),
        message=f"Quanto fica {query} no débito?",
    )
    assert response.results[-1].missing_fields == ("product_reference",)
    assert "Não encontrei" not in response.text


def test_payment_word_reference_in_update_is_dropped(app):
    turn(app, search("Violão"))
    turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 2}, payment_method="pix"
        ),
    )
    response = update(
        app,
        product_reference={"kind": "query", "query": "no pix"},
        quantity=1,
    )
    assert response.results[-1].data.name == "Violão B"


def test_payment_word_only_update_asks_for_product_again(app):
    turn(app, payment(quantity=1, payment_method="pix"))
    response = update(app, product_reference={"kind": "query", "query": "pix"})
    assert response.results[-1].missing_fields == ("product_reference",)


@pytest.mark.parametrize("query", ["avista", "cartaocredito"])
def test_glued_words_are_not_payment_only(app, query):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": query},
            quantity=1,
            payment_method="pix",
        ),
    )
    assert response.results[-1].reason_code == "NO_CATALOG_MATCH"


def test_search_without_results_keeps_the_list(app):
    turn(app, search("Violão"))
    turn(app, search("Bateria rosa"))
    assert app.session.displayed_product_ids == (10, 20)


def quote_piano_pix(app):
    turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Piano"},
            quantity=1,
            payment_method="pix",
        ),
        message="Uma unidade do Piano no PIX",
    )


def test_payment_copied_to_another_product_is_discarded(app):
    quote_piano_pix(app)
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Violão A"},
            quantity=1,
            payment_method="pix",
            installments=None,
        ),
        message="Adicione uma unidade do Violão A",
    )
    assert response.results[-1].missing_fields == ("payment_method",)


@pytest.mark.parametrize(
    "reference",
    [{"kind": "query", "query": "Piano"}, {"kind": "selected"}],
)
def test_same_product_reuses_payment_with_notice(app, reference):
    quote_piano_pix(app)
    response = turn(
        app,
        payment(product_reference=reference, quantity=2, payment_method="pix"),
        message="E se forem 2 unidades do Piano?",
    )
    assert response.results[-1].data.payment_method == "pix"
    assert "cotação anterior" in response.text


def test_ordinal_to_selected_product_reuses_payment(app):
    turn(app, search("Violão"))
    turn(
        app,
        payment(
            product_reference={"kind": "ordinal", "ordinal": 1},
            quantity=1,
            payment_method="pix",
        ),
        message="O primeiro no pix",
    )
    response = turn(
        app,
        payment(product_reference={"kind": "ordinal", "ordinal": 1}, quantity=2),
        message="Duas do primeiro",
    )
    assert response.results[-1].data.payment_method == "pix"


@pytest.mark.parametrize(
    ("method", "message"),
    [
        ("debit", "uma no cartão"),
        ("credit", "uma no cartão"),
        ("credit", "uma parcelado"),
        ("boleto", "uma no boleto"),
    ],
)
def test_typed_payment_is_accepted(app, method, message):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Piano"},
            quantity=1,
            payment_method=method,
        ),
        message=message,
    )
    assert response.results[-1].data.payment_method == method


def after_pix(app):
    quote_piano_pix(app)
    return {"kind": "selected"}


@pytest.mark.parametrize(
    ("message", "fields", "method"),
    [
        ("e no credito?", {"payment_method": "credit"}, "credit"),
        ("seis vezes", {"payment_method": "credit", "installments": 6}, "credit"),
        ("no boleto", {"payment_method": "boleto"}, "boleto"),
    ],
)
def test_other_method_from_model_replaces_earlier_pix(app, message, fields, method):
    reference = after_pix(app)
    response = turn(
        app, payment(product_reference=reference, **fields), message=message
    )
    assert response.results[-1].data.payment_method == method
    assert "PIX:" not in response.text


@pytest.mark.parametrize(
    ("message", "fields"),
    [
        ("e no credito?", {"payment_method": "pix"}),
        ("no débito", {}),
        ("e em dinheiro?", {}),
        ("à vista", {"payment_method": "pix"}),
        ("não no pix", {}),
        ("não uso pix", {"payment_method": "pix"}),
        ("pix não, crédito", {"payment_method": "pix"}),
        ("em vez de pix, boleto", {"payment_method": "pix"}),
        ("pix e cartão", {"payment_method": "pix"}),
        ("e em 10 vezes?", {"payment_method": "pix", "installments": 10}),
    ],
)
def test_payment_doubt_asks_instead_of_discounting(app, message, fields):
    reference = after_pix(app)
    response = turn(
        app, payment(product_reference=reference, **fields), message=message
    )
    assert "payment_method" in response.results[-1].missing_fields


def test_product_name_with_count_does_not_infer_credit(app):
    response = turn(
        app,
        payment(product_reference={"kind": "query", "query": "Piano"}, quantity=1),
        message="quanto custa o Piano 2X?",
    )
    assert response.results[-1].missing_fields == ("payment_method",)


def test_bare_number_reference_is_not_a_payment_word(app):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "310"},
            quantity=1,
            payment_method="pix",
        ),
        message="o 310 no pix",
    )
    assert response.results[-1].reason_code == "NO_CATALOG_MATCH"


@pytest.mark.parametrize("reference", [{"kind": "selected"}, None])
def test_naming_another_product_blocks_reuse(app, reference):
    quote_piano_pix(app)
    fields = {"product_reference": reference} if reference else {}
    response = turn(app, payment(**fields), message="e o Violão A?")
    assert "cotação anterior" not in response.text
    assert "payment_method" in response.results[-1].missing_fields


def test_pix_search_then_dependent_quote_keep_the_mention(app):
    response = turn(
        app,
        {"type": "product_search", "query": "Piano", "payment_method": "pix"},
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
        message="Tem Piano? Quanto no pix?",
    )
    assert response.results[-1].data.payment_method == "pix"


def test_installments_alone_are_not_accepted_as_update(app):
    turn(
        app,
        payment(product_reference={"kind": "query", "query": "Piano"}, quantity=1),
    )
    response = update(app, message="sei la", installments=12)
    assert "Não consegui aplicar" in response.text


def test_method_named_once_applies_to_first_request_only(app):
    response = turn(
        app,
        payment(
            product_reference={"kind": "query", "query": "Violão A"},
            quantity=1,
            payment_method="pix",
        ),
        payment(
            product_reference={"kind": "query", "query": "Piano"},
            quantity=1,
            payment_method="pix",
        ),
        message="Violão A no pix e também o Piano, 1 de cada",
    )
    assert response.results[0].data.payment_method == "pix"
    assert response.results[-1].missing_fields == ("payment_method",)


def test_search_drops_copied_method_and_keeps_typed_one(app):
    copied = turn(
        app,
        {"type": "product_search", "query": "Piano", "payment_method": "pix"},
        message="Tem piano?",
    )
    assert copied.results[0].data.products[0].payment_method is None
    typed = turn(
        app,
        {"type": "product_search", "query": "Piano", "payment_method": "pix"},
        message="Tem piano no pix?",
    )
    assert typed.results[0].data.products[0].payment_method == "pix"


def test_update_with_method_and_installments_is_accepted(app):
    turn(
        app,
        payment(product_reference={"kind": "query", "query": "Piano"}, quantity=1),
    )
    response = update(
        app, message="no crédito em 6x", payment_method="credit", installments=6
    )
    assert response.results[-1].data.installments == 6


def test_copied_method_does_not_block_valid_update(app):
    turn(
        app,
        {
            "type": "shipping_quote",
            "product_reference": {"kind": "query", "query": "Piano"},
            "quantity": 1,
            "payment_method": "boleto",
        },
    )
    response = update(
        app,
        message="Campo Grande",
        destination={"city": "Campo Grande"},
        payment_method="boleto",
    )
    assert response.results[-1].data.quote.payment_method == "boleto"


def test_name_from_history_reuses_facts_for_follow_up(app):
    quote_piano_pix(app)
    response = turn(
        app,
        payment(product_reference={"kind": "query", "query": "Piano"}, quantity=2),
        message="E se forem 2 unidades?",
    )
    assert response.results[-1].data.payment_method == "pix"
    assert "cotação anterior" in response.text


def test_name_from_history_does_not_reuse_when_another_product_is_named(app):
    quote_piano_pix(app)
    response = turn(
        app,
        payment(product_reference={"kind": "query", "query": "Piano"}, quantity=1),
        message="adicione um Violão",
    )
    assert response.results[-1].missing_fields == ("payment_method",)


def test_pending_facts_reuse_is_announced(app):
    turn(
        app,
        {
            "type": "shipping_quote",
            "product_reference": {"kind": "query", "query": "Piano"},
            "quantity": 2,
            "payment_method": "pix",
        },
    )
    response = turn(
        app,
        payment(product_reference={"kind": "selected"}),
        message="quanto fica?",
    )
    assert "cotação anterior" in response.text
