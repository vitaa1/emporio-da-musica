"""Python-owned outcomes, structurally typed but not calculated or authorized here."""

from datetime import date
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import Field, NonNegativeInt, TypeAdapter, model_validator

from .common import (
    Contract,
    Installments,
    Money,
    PaymentMethod,
    Percentage,
    PolicyReference,
    PositiveInt,
    Text,
)


class ProductQuote(Contract):
    product_id: PositiveInt
    name: Text
    quantity: PositiveInt
    availability: Literal[
        "available", "insufficient_stock", "discontinued", "coming_soon"
    ]
    list_unit_price_brl: Money
    promotion_percent: Percentage | None
    payment_method: PaymentMethod | None
    installments: Installments | None
    final_total_brl: Money
    assumptions: tuple[Text, ...] = ()
    # Credit installments (§3.1): the amount of each installment when the requested
    # count meets the documented minimum; the first carries any remaining cents.
    installment_amount_brl: Money | None = None
    first_installment_brl: Money | None = None
    # For credit without a count: the largest count in 4–12 meeting the minimum.
    max_installments: Installments | None = None
    # Filled when no payment was requested, to present every payment option.
    stock_quantity: NonNegativeInt | None = None
    pix_total_brl: Money | None = None


class CatalogGuide(Contract):
    """A broad request answered with a question instead of a long list."""

    category: Text | None = None
    brands: tuple[Text, ...] = ()
    lowest_price_brl: Money | None = None
    highest_price_brl: Money | None = None


class CatalogData(Contract):
    products: tuple[ProductQuote, ...]
    total_matches: PositiveInt | None = None
    guide: CatalogGuide | None = None


class OrderData(Contract):
    order_id: PositiveInt
    status: Literal["pending", "confirmed", "shipped", "delivered", "cancelled"]
    recorded_total_brl: Money
    tracking_code: Text | None = None
    estimated_delivery: date | None = None


class ShippingData(Contract):
    quote: ProductQuote
    subtotal_brl: Money
    freight_brl: Money
    destination_city: Text
    assumptions: tuple[Text, ...] = ()


class AssessedCondition(Contract):
    name: Text
    state: Literal["satisfied", "not_satisfied", "unknown", "requires_review"]
    provenance: Literal["system_record", "customer_declaration", "policy", "unknown"]


class ReturnData(Contract):
    reason: Literal["withdrawal", "defect", "preference"]
    assessment: Literal["conditions_met", "conditions_not_met", "requires_review"]
    conditions: tuple[AssessedCondition, ...]


class PolicyData(Contract):
    answer: Text
    policy_references: Annotated[tuple[PolicyReference, ...], Field(min_length=1)]


class ComplaintData(Contract):
    template: Literal["complaint_acknowledgment"] = "complaint_acknowledgment"


class OutOfScopeData(Contract):
    template: Literal["scope_redirect", "accessory_redirect"] = "scope_redirect"


class SmallTalkData(Contract):
    template: Literal["greeting", "thanks", "goodbye"]


Status = Literal[
    "success",
    "not_found",
    "needs_information",
    "requires_confirmation",
    "unauthorized",
    "unavailable",
    "error",
]
DataT = TypeVar("DataT")


class Result(Contract, Generic[DataT]):
    result_id: UUID = Field(default_factory=uuid4)
    status: Status
    data: DataT | None = None
    missing_fields: tuple[Text, ...] = ()
    reason_code: Text | None = None
    policy_references: tuple[PolicyReference, ...] = ()

    @model_validator(mode="after")
    def consistent_state(self):
        if self.status == "success":
            if self.data is None or self.missing_fields:
                raise ValueError(
                    "Successful results require data and no missing fields"
                )
        elif self.status == "needs_information":
            if not self.missing_fields or self.data is not None:
                raise ValueError("Clarifications require missing fields and no data")
        elif self.data is not None or self.missing_fields:
            raise ValueError(
                "Other result states must not carry data or missing fields"
            )
        if self.status != "success" and self.reason_code is None:
            raise ValueError("Non-success results require a Python reason code")
        return self


class ProductSearchResult(Result[CatalogData]):
    operation: Literal["product_search"] = "product_search"


class OrderStatusResult(Result[OrderData]):
    operation: Literal["order_status"] = "order_status"


class PaymentOptionsResult(Result[ProductQuote]):
    operation: Literal["payment_options"] = "payment_options"


class ShippingQuoteResult(Result[ShippingData]):
    operation: Literal["shipping_quote"] = "shipping_quote"


class ReturnAssessmentResult(Result[ReturnData]):
    operation: Literal["return_assessment"] = "return_assessment"


class PolicyQuestionResult(Result[PolicyData]):
    operation: Literal["policy_question"] = "policy_question"


class ComplaintResult(Result[ComplaintData]):
    operation: Literal["complaint"] = "complaint"


class OutOfScopeResult(Result[OutOfScopeData]):
    operation: Literal["out_of_scope"] = "out_of_scope"


class SmallTalkResult(Result[SmallTalkData]):
    operation: Literal["small_talk"] = "small_talk"


OperationResult = Annotated[
    ProductSearchResult
    | OrderStatusResult
    | PaymentOptionsResult
    | ShippingQuoteResult
    | ReturnAssessmentResult
    | PolicyQuestionResult
    | ComplaintResult
    | OutOfScopeResult
    | SmallTalkResult,
    Field(discriminator="operation"),
]
RESULT_ADAPTER = TypeAdapter(OperationResult)
