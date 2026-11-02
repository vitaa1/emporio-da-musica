"""Shared strict types for external proposals and internal records."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_INTENTS = 5
MAX_HISTORY = 20
MAX_MESSAGE_LENGTH = 4000
MAX_PENDING = 5
MAX_RESPONSE_BYTES = 32000


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )


Text = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH
    ),
]
PositiveInt = Annotated[int, Field(gt=0)]
Installments = Annotated[int, Field(ge=1, le=12)]
Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, decimal_places=2)]
Percentage = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)]
PaymentMethod = Literal["pix", "debit", "credit", "boleto", "combined"]
Operation = Literal[
    "product_search",
    "order_status",
    "payment_options",
    "shipping_quote",
    "return_assessment",
    "policy_question",
    "complaint",
    "out_of_scope",
    "small_talk",
]
PolicyReference = Literal[
    "1",
    "1.1",
    "1.2",
    "2",
    "3",
    "3.1",
    "4",
    "4.1",
    "4.2",
    "4.3",
    "4.4",
    "5",
    "5.1",
    "5.2",
    "5.3",
    "6",
    "6.1",
    "6.2",
    "7",
    "7.1",
    "7.2",
    "7.3",
    "8",
    "8.1",
    "8.2",
    "8.3",
    "9",
    "10",
]
