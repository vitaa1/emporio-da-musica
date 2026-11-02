"""Contract boundaries reject malformed proposals before any business execution."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from emporio_da_musica.contracts.common import MAX_HISTORY, MAX_RESPONSE_BYTES
from emporio_da_musica.contracts.dates import store_today
from emporio_da_musica.contracts.intents import (
    ClarificationUpdate,
    IntentTurn,
    ProposalError,
    parse_proposal,
)
from emporio_da_musica.contracts.results import (
    RESULT_ADAPTER,
    CatalogData,
    OrderData,
    OrderStatusResult,
    PolicyData,
    ProductQuote,
    ProductSearchResult,
)
from emporio_da_musica.contracts.session import (
    ConversationMessage,
    DeclaredFacts,
    PendingOperation,
    RecordReferences,
    SessionState,
    create_session,
)
from emporio_da_musica.data import load_snapshot
from emporio_da_musica.provider import (
    ProviderError,
    ProviderRequest,
    extract_proposal,
)


def clock():
    return datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)


def parse(*intents):
    return parse_proposal(json.dumps({"intents": list(intents)}), clock=clock)


@pytest.mark.parametrize(
    "kind",
    [
        "product_search",
        "order_status",
        "payment_options",
        "shipping_quote",
        "return_assessment",
        "policy_question",
        "complaint",
        "out_of_scope",
        "small_talk",
    ],
)
def test_every_intent_and_missing_information(kind):
    proposal = parse({"type": kind})
    assert proposal.intents[0].type == kind
    assert all(
        value is None
        for key, value in proposal.intents[0].model_dump().items()
        if key != "type"
    )


def test_multiple_intents_preserve_source_order_and_unknown_quantity():
    proposal = parse(
        {"type": "product_search", "query": "guitar", "max_price_brl": "500.25"},
        {"type": "shipping_quote", "payment_method": "pix"},
        {"type": "policy_question", "topic": "hours"},
    )
    assert [item.type for item in proposal.intents] == [
        "product_search",
        "shipping_quote",
        "policy_question",
    ]
    assert proposal.intents[0].max_price_brl == Decimal("500.25")
    assert proposal.intents[0].quantity is None
    assert proposal.intents[1].quantity is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("customer_id", 1),
        ("price", "1.00"),
        ("discount", 90),
        ("authorized", True),
        ("function", "eval"),
        ("product_id", 10),
        ("quantity", True),
        ("quantity", 0),
        ("quantity", "1"),
        ("quantity", 1.5),
        ("available_only", "false"),
        ("max_price_brl", 100),
        ("max_price_brl", 1.5),
        ("max_price_brl", "NaN"),
        ("max_price_brl", "Infinity"),
        ("max_price_brl", "-1"),
        ("max_price_brl", "1.001"),
        ("payment_method", "cash"),
        ("installments", 13),
        ("installments", True),
    ],
)
def test_invalid_types_and_authoritative_fields(field, value):
    with pytest.raises(ProposalError, match="Invalid model proposal"):
        parse({"type": "product_search", field: value})


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        "null",
        '{"intents":[]}',
        '{"intents":[{"type":"unknown"}]}',
        '{"intents":[{"type":"small_talk","kind":"thanks"}],"identity":1}',
        '{"intents":[{"type":"small_talk","type":"order_status"}]}',
        '{"intents":[{"type":"shipping_quote","destination":{"city":"X","eligible":true}}]}',
        '{"intents":[{"type":"return_assessment","condition":{"signs_of_use":0}}]}',
        '{"intents":[{"type":"payment_options","product_reference":{"kind":"selected","product_id":1}}]}',
    ],
)
def test_invalid_envelopes_and_nested_injection(raw):
    with pytest.raises(ProposalError):
        parse_proposal(raw, clock=clock)


def test_bounds():
    assert len(parse(*[{"type": "small_talk"}] * 5).intents) == 5
    with pytest.raises(ProposalError):
        parse(*[{"type": "small_talk"}] * 6)
    with pytest.raises(ProposalError):
        parse_proposal(" " * (MAX_RESPONSE_BYTES + 1), clock=clock)
    with pytest.raises(ValidationError):
        ProviderRequest(message="a" * 4001)


@pytest.mark.parametrize(
    "reference",
    [
        {"kind": "query", "query": "Yamaha"},
        {"kind": "selected"},
        {"kind": "ordinal", "ordinal": 2},
    ],
)
def test_references_remain_unresolved(reference):
    intent = parse({"type": "payment_options", "product_reference": reference}).intents[
        0
    ]
    assert intent.product_reference.model_dump() == reference


def test_combined_payment_and_missing_condition_booleans():
    intent = parse({"type": "shipping_quote", "payment_method": "combined"}).intents[0]
    assert intent.payment_method == "combined"
    intent = parse(
        {"type": "return_assessment", "condition": {"signs_of_use": False}}
    ).intents[0]
    assert intent.condition.signs_of_use is False
    assert intent.condition.customized is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-11-01", date(2026, 11, 1)),
        ("today", date(2026, 11, 1)),
        ("yesterday", date(2026, 10, 31)),
        ("day_before_yesterday", date(2026, 10, 30)),
    ],
)
def test_receipt_date_resolution_uses_store_day(raw, expected):
    result = parse({"type": "return_assessment", "received_at": raw})
    assert result.intents[0].received_at == expected


@pytest.mark.parametrize(
    "raw", ["2026-11-02", "next Monday", "01/11/2026", "2026-02-30", 0]
)
def test_invalid_or_future_receipt_date(raw):
    with pytest.raises(ProposalError):
        parse({"type": "return_assessment", "received_at": raw})


def test_injected_clock_requires_timezone_and_handles_local_midnight():
    with pytest.raises(ValueError, match="timezone-aware"):
        store_today(lambda: datetime(2026, 11, 2))
    assert store_today(clock) == date(2026, 11, 1)
    assert store_today(lambda: datetime(2026, 11, 2, 4, tzinfo=timezone.utc)) == date(
        2026, 11, 2
    )


def pending_shipping():
    intent = parse({"type": "shipping_quote", "quantity": 2}).intents[0]
    return PendingOperation(
        declarations=DeclaredFacts(intent=intent),
        requested_fields=("payment_method", "destination"),
        records=RecordReferences(product_id=10),
    )


def update(pending, **fields):
    return parse_proposal(
        json.dumps(
            {
                "pending_id": pending.pending_id,
                "update": {"type": "shipping_quote", **fields},
            }
        ),
        clock=clock,
    )


def test_pending_update_is_scoped_and_invalidates_resolved_references():
    pending = pending_shipping()
    facts, missing, records = pending.apply_update(
        update(pending, payment_method="pix"), clock=clock
    )
    assert facts.source == "customer_declaration"
    assert facts.intent.quantity == 2
    assert facts.intent.payment_method == "pix"
    assert missing == ("destination",)
    assert records.product_id is None
    assert pending.records.product_id == 10
    assert pending.declarations.intent.payment_method is None


@pytest.mark.parametrize(
    "fields", [{}, {"quantity": 4}, {"order_id": 1}, {"customer_id": 1}]
)
def test_clarification_cannot_mutate_unrequested_or_foreign_fields(fields):
    pending = pending_shipping()
    with pytest.raises(ValueError):
        pending.apply_update(update(pending, **fields), clock=clock)


def test_clarification_rejects_wrong_id_type_and_retains_unknown():
    pending = pending_shipping()
    with pytest.raises(ValueError):
        pending.apply_update(
            ClarificationUpdate(
                pending_id="wrong", update=update(pending, payment_method="pix").update
            ),
            clock=clock,
        )
    wrong_type = parse_proposal(
        json.dumps(
            {
                "pending_id": pending.pending_id,
                "update": {"type": "order_status", "order_id": 1},
            }
        ),
        clock=clock,
    )
    with pytest.raises(ValueError):
        pending.apply_update(wrong_type, clock=clock)
    _, missing, _ = pending.apply_update(
        update(pending, payment_method=None), clock=clock
    )
    assert missing == ("payment_method", "destination")


def test_session_identity_and_bounded_history():
    snapshot = load_snapshot(Path(__file__).resolve().parents[1] / "data" / "demo")
    identifier = next(iter(snapshot.customers))
    session = create_session(snapshot, identifier)
    assert create_session(snapshot).simulated_customer_id is None
    for invalid in (True, "1", -1, 999999):
        with pytest.raises(ValueError):
            create_session(snapshot, invalid)
    with pytest.raises(ValidationError):
        session.simulated_customer_id = identifier + 1
    for n in range(MAX_HISTORY + 3):
        session = session.append_message(
            ConversationMessage(role="user", content=str(n))
        )
    assert len(session.history) == MAX_HISTORY
    assert session.history[0].content == "3"
    assert session.simulated_customer_id == identifier
    with pytest.raises(ValidationError):
        SessionState(displayed_product_ids=(1,), selected_product_id=2)
    with pytest.raises(ValidationError):
        ProviderRequest(message="hello", simulated_customer_id=identifier)


def test_pending_allowlist_cannot_request_identity():
    intent = parse({"type": "order_status"}).intents[0]
    with pytest.raises(ValidationError):
        PendingOperation(
            declarations=DeclaredFacts(intent=intent), requested_fields=("customer_id",)
        )


def quote():
    return ProductQuote(
        product_id=10,
        name="Demo",
        quantity=1,
        availability="discontinued",
        list_unit_price_brl=Decimal("500"),
        promotion_percent=None,
        payment_method=None,
        installments=None,
        final_total_brl=Decimal("500"),
    )


def test_typed_results_and_business_outcomes():
    result = ProductSearchResult(
        status="success", data=CatalogData(products=(quote(),))
    )
    restored = RESULT_ADAPTER.validate_json(result.model_dump_json())
    assert restored == result
    assert result.data.products[0].availability == "discontinued"
    order = OrderStatusResult(
        status="success",
        data=OrderData(
            order_id=1, status="delivered", recorded_total_brl=Decimal("499.99")
        ),
    )
    assert order.data.estimated_delivery is None
    assert order.result_id != result.result_id


@pytest.mark.parametrize(
    "status",
    ["not_found", "requires_confirmation", "unauthorized", "unavailable", "error"],
)
def test_non_success_results_cannot_expose_order_data(status):
    result = OrderStatusResult(status=status, reason_code="UNAVAILABLE")
    assert result.data is None
    with pytest.raises(ValidationError):
        OrderStatusResult(
            status=status,
            reason_code="UNAVAILABLE",
            data=OrderData(
                order_id=1, status="delivered", recorded_total_brl=Decimal("1")
            ),
        )


def test_result_status_invariants_and_operation_data_matching():
    with pytest.raises(ValidationError):
        OrderStatusResult(status="success")
    with pytest.raises(ValidationError):
        OrderStatusResult(status="needs_information", reason_code="MISSING")
    result = OrderStatusResult(
        status="needs_information", reason_code="MISSING", missing_fields=("order_id",)
    )
    assert result.missing_fields == ("order_id",)
    with pytest.raises(ValidationError):
        OrderStatusResult(status="success", data=CatalogData(products=()))
    with pytest.raises(ValidationError):
        PolicyData(answer="Example", policy_references=("99",))


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_provider_boundary_repairs_once_without_dispatch():
    provider = FakeProvider(
        ["invalid", '{"intents":[{"type":"small_talk","kind":"thanks"}]}']
    )
    result = extract_proposal(provider, ProviderRequest(message="thanks"), clock=clock)
    assert isinstance(result, IntentTurn)
    assert [request.repair_requested for request in provider.requests] == [False, True]
    provider = FakeProvider(["invalid", "still invalid"])
    with pytest.raises(ProposalError):
        extract_proposal(provider, ProviderRequest(message="hello"), clock=clock)
    assert len(provider.requests) == 2


def test_provider_failure_does_not_trigger_schema_repair():
    provider = FakeProvider([ProviderError("Service unavailable")])
    with pytest.raises(ProviderError):
        extract_proposal(provider, ProviderRequest(message="hello"), clock=clock)
    assert len(provider.requests) == 1


def test_clarification_preserves_prior_nested_declarations():
    intent = parse(
        {"type": "return_assessment", "condition": {"original_packaging": True}}
    ).intents[0]
    pending = PendingOperation(
        declarations=DeclaredFacts(intent=intent), requested_fields=("condition",)
    )
    clarification = parse_proposal(
        json.dumps(
            {
                "pending_id": pending.pending_id,
                "update": {
                    "type": "return_assessment",
                    "condition": {"signs_of_use": False},
                },
            }
        ),
        clock=clock,
    )
    facts, _, _ = pending.apply_update(clarification, clock=clock)
    assert facts.intent.condition.original_packaging is True
    assert facts.intent.condition.signs_of_use is False
    assert facts.intent.condition.customized is None


def test_schema_exposes_discriminator_and_decimal_string_budget():
    schema = IntentTurn.model_json_schema()
    assert (
        schema["properties"]["intents"]["items"]["discriminator"]["propertyName"]
        == "type"
    )
    alternatives = schema["$defs"]["ProductSearch"]["properties"]["max_price_brl"][
        "anyOf"
    ]
    assert {option["type"] for option in alternatives} == {"string", "null"}


def test_excessive_intents_require_narrowing_without_repair():
    from emporio_da_musica.contracts.intents import RequestTooBroadError

    provider = FakeProvider([json.dumps({"intents": [{"type": "small_talk"}] * 6})])
    with pytest.raises(RequestTooBroadError):
        extract_proposal(
            provider, ProviderRequest(message="many requests"), clock=clock
        )
    assert len(provider.requests) == 1
