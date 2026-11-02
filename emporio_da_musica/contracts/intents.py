"""Only these fields may cross from a model proposal into Python validation."""

import json
import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, ValidationInfo, field_validator

from .common import (
    MAX_INTENTS,
    MAX_RESPONSE_BYTES,
    Contract,
    Installments,
    Money,
    PaymentMethod,
    PositiveInt,
    Text,
)
from .dates import Clock, resolve_receipt_date, store_today


def _decimal_string(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]+(?:\.[0-9]{1,2})?", value
    ):
        raise ValueError("Amount must be a nonnegative decimal string")
    return Decimal(value)


Budget = Annotated[
    Money,
    BeforeValidator(
        _decimal_string,
        json_schema_input_type=Annotated[
            str, Field(pattern=r"^[0-9]+(?:\.[0-9]{1,2})?$")
        ],
    ),
]


class QueryReference(Contract):
    kind: Literal["query"]
    query: Text


class SelectedReference(Contract):
    kind: Literal["selected"]


class OrdinalReference(Contract):
    kind: Literal["ordinal"]
    ordinal: PositiveInt


ProductReference = Annotated[
    QueryReference | SelectedReference | OrdinalReference, Field(discriminator="kind")
]


class Destination(Contract):
    city: Text | None = None
    state: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None
    postal_code: Annotated[str, Field(pattern=r"^[0-9]{5}-?[0-9]{3}$")] | None = None


class Condition(Contract):
    original_packaging: bool | None = None
    signs_of_use: bool | None = None
    complete_accessories_manuals: bool | None = None
    customized: bool | None = None
    final_sale_notice: bool | None = None


class ProductSearch(Contract):
    type: Literal["product_search"]
    query: Text | None = None
    category: Text | None = None
    max_price_brl: Budget | None = None
    available_only: bool | None = None
    quantity: PositiveInt | None = None
    payment_method: PaymentMethod | None = None
    installments: Installments | None = None


class OrderStatus(Contract):
    type: Literal["order_status"]
    order_id: PositiveInt | None = None


class PaymentOptions(Contract):
    type: Literal["payment_options"]
    product_reference: ProductReference | None = None
    quantity: PositiveInt | None = None
    payment_method: PaymentMethod | None = None
    installments: Installments | None = None


class ShippingQuote(Contract):
    type: Literal["shipping_quote"]
    product_reference: ProductReference | None = None
    quantity: PositiveInt | None = None
    destination: Destination | None = None
    payment_method: PaymentMethod | None = None
    installments: Installments | None = None


class ReturnAssessment(Contract):
    type: Literal["return_assessment"]
    order_id: PositiveInt | None = None
    reason: Literal["withdrawal", "defect", "preference"] | None = None
    purchase_channel: Literal["online", "in_store"] | None = None
    received_at: date | None = None
    condition: Condition | None = None

    @field_validator("received_at", mode="before", json_schema_input_type=str | None)
    @classmethod
    def validate_receipt(cls, value, info: ValidationInfo):
        if value is None:
            return None
        today = (info.context or {}).get("today")
        if type(today) is not date:
            raise ValueError("Receipt validation requires an injected store date")
        if type(value) is date:
            if value > today:
                raise ValueError("Receipt date cannot be in the future")
            return value
        if not isinstance(value, str):
            raise ValueError("Receipt must be an ISO date or supported relative date")
        return resolve_receipt_date(value, today)


class PolicyQuestion(Contract):
    type: Literal["policy_question"]
    topic: Text | None = None
    question: Text | None = None


class Complaint(Contract):
    type: Literal["complaint"]
    description: Text | None = None


class OutOfScope(Contract):
    type: Literal["out_of_scope"]
    topic: Text | None = None


class SmallTalk(Contract):
    type: Literal["small_talk"]
    kind: Literal["greeting", "thanks", "goodbye"] | None = None


Intent = Annotated[
    ProductSearch
    | OrderStatus
    | PaymentOptions
    | ShippingQuote
    | ReturnAssessment
    | PolicyQuestion
    | Complaint
    | OutOfScope
    | SmallTalk,
    Field(discriminator="type"),
]


class IntentTurn(Contract):
    intents: Annotated[list[Intent], Field(min_length=1, max_length=MAX_INTENTS)]


class ClarificationUpdate(Contract):
    pending_id: Text
    update: Intent


Proposal = IntentTurn | ClarificationUpdate


class ProposalError(ValueError):
    """Stable failure without echoing model output or personal values."""


class RequestTooBroadError(ProposalError):
    """The controller must ask the customer to narrow the request."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_proposal(raw: str, *, clock: Clock) -> Proposal:
    """Validate a full turn or a clarification; never dispatch any operation."""
    today = store_today(clock)
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError
        data = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(data, dict):
            raise ValueError
        if isinstance(data.get("intents"), list) and len(data["intents"]) > MAX_INTENTS:
            raise RequestTooBroadError("Please narrow the request to five intents")
        model = ClarificationUpdate if "pending_id" in data else IntentTurn
        return model.model_validate(data, context={"today": today})
    except RequestTooBroadError:
        raise
    except (ValueError, ArithmeticError, RecursionError):
        raise ProposalError("Invalid model proposal") from None
