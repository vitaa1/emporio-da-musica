"""Deterministic return and exchange assessments (manual §§4.1–4.4).

The assessment states which documented conditions are satisfied, unknown, or need
store review. It never requests, approves, or performs a refund or exchange.
"""

from datetime import date

from .contracts.intents import ReturnAssessment
from .contracts.results import AssessedCondition, ReturnAssessmentResult, ReturnData
from .data.records import Order

WITHDRAWAL_DAYS = 7
DEFECT_DAYS = 30
REFERENCES = {
    "withdrawal": ("4.1",),
    "defect": ("4.2", "4.4"),
    "preference": ("4.3", "4.4"),
}


def required_fields(intent: ReturnAssessment) -> tuple[str, ...]:
    """Facts the customer must supply before an individual assessment."""
    if intent.reason is None:
        return ("reason",)
    if intent.reason == "withdrawal":
        if intent.purchase_channel == "in_store":
            # In-store purchases fall outside §4.1 regardless of other facts.
            return ()
        missing = []
        if intent.purchase_channel is None:
            missing.append("purchase_channel")
        if intent.received_at is None:
            missing.append("received_at")
        if intent.condition is None:
            missing.append("condition")
        return tuple(missing)
    if intent.reason == "defect":
        # The 30-day window starts at purchase, taken from the order record.
        return () if intent.order_id is not None else ("order_id",)
    return () if intent.condition is not None else ("condition",)


def _condition(name, state, provenance):
    return AssessedCondition(name=name, state=state, provenance=provenance)


def _declared(name, value, expected):
    """A customer-declared boolean compared with the value the policy requires."""
    if value is None:
        return _condition(name, "unknown", "unknown")
    state = "satisfied" if value == expected else "not_satisfied"
    return _condition(name, state, "customer_declaration")


def _delivered(order):
    if order.status == "delivered":
        return _condition("order_delivered", "satisfied", "system_record")
    # The snapshot is historical; a customer may hold the product anyway.
    return _condition("order_delivered", "requires_review", "system_record")


def _window(name, start, today, days, provenance):
    # Day zero is the starting date; the stated last day is included.
    elapsed = (today - start).days
    state = "satisfied" if elapsed <= days else "not_satisfied"
    return _condition(name, state, provenance)


def _withdrawal(intent, order, today):
    if intent.purchase_channel == "in_store":
        return [_condition("online_purchase", "not_satisfied", "customer_declaration")]
    window = _window(
        "within_7_days_of_receipt",
        intent.received_at,
        today,
        WITHDRAWAL_DAYS,
        "customer_declaration",
    )
    conditions = [_condition("online_purchase", "satisfied", "customer_declaration")]
    if order is not None and intent.received_at < order.order_date:
        # The record contradicts the declared receipt; the window cannot be trusted.
        window = _condition(window.name, "requires_review", "customer_declaration")
        conditions += [
            window,
            _delivered(order),
            _condition("receipt_after_order", "requires_review", "system_record"),
        ]
    else:
        conditions.append(window)
        if order is not None:
            conditions.append(_delivered(order))
    condition = intent.condition
    conditions += [
        _declared("original_packaging", condition.original_packaging, True),
        _declared("no_signs_of_use", condition.signs_of_use, False),
        _declared(
            "complete_accessories_manuals",
            condition.complete_accessories_manuals,
            True,
        ),
    ]
    # §4.4 lists exchange exclusions; its effect on withdrawal is not stated.
    if condition.customized:
        conditions.append(
            _condition("not_customized", "requires_review", "customer_declaration")
        )
    if condition.final_sale_notice:
        conditions.append(
            _condition("not_final_sale", "requires_review", "customer_declaration")
        )
    return conditions


def _exclusions(condition):
    customized = condition.customized if condition else None
    final_sale = condition.final_sale_notice if condition else None
    return [
        _declared("not_customized", customized, False),
        _declared("not_final_sale", final_sale, False),
    ]


def _defect(intent, order, today):
    return [
        _delivered(order),
        _window(
            "within_30_days_of_purchase",
            order.order_date,
            today,
            DEFECT_DAYS,
            "system_record",
        ),
        # A declared defect still needs inspection (misuse is not covered).
        _condition("manufacturing_defect", "requires_review", "customer_declaration"),
        *_exclusions(intent.condition),
    ]


def _preference(intent, order):
    condition = intent.condition
    conditions = [
        # §4.3 does not say whether the seven days start at purchase or receipt.
        _condition("preference_window", "requires_review", "policy"),
        _declared("original_packaging", condition.original_packaging, True),
        _declared("no_signs_of_use", condition.signs_of_use, False),
        *_exclusions(condition),
        _condition("desired_product_available", "unknown", "unknown"),
    ]
    if order is not None:
        conditions.insert(1, _delivered(order))
    return conditions


def assess_return(
    intent: ReturnAssessment, order: Order | None, today: date
) -> ReturnAssessmentResult:
    """Assess an intent whose required facts are present and order is authorized."""
    if intent.reason == "withdrawal":
        conditions = _withdrawal(intent, order, today)
    elif intent.reason == "defect":
        conditions = _defect(intent, order, today)
    else:
        conditions = _preference(intent, order)
    states = {c.state for c in conditions}
    if "not_satisfied" in states:
        assessment = "conditions_not_met"
    elif states & {"unknown", "requires_review"}:
        assessment = "requires_review"
    else:
        assessment = "conditions_met"
    references = REFERENCES[intent.reason]
    if any(
        c.name == "within_30_days_of_purchase" and c.state == "not_satisfied"
        for c in conditions
    ):
        references += ("8.2",)
    return ReturnAssessmentResult(
        status="success",
        data=ReturnData(
            reason=intent.reason, assessment=assessment, conditions=tuple(conditions)
        ),
        policy_references=references,
    )
