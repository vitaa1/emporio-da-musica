"""Session-only, Python-owned state and narrowly scoped clarification updates."""

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from emporio_da_musica.data.records import Snapshot

from .common import MAX_HISTORY, MAX_PENDING, Contract, PositiveInt, Text
from .dates import Clock, store_today
from .intents import ClarificationUpdate, Intent


class ConversationMessage(Contract):
    role: Literal["user", "assistant"]
    content: Text


class RecordReferences(Contract):
    """Resolved by Python; never accepted from the provider parser."""

    source: Literal["system_record"] = "system_record"
    product_id: PositiveInt | None = None
    order_id: PositiveInt | None = None


class DeclaredFacts(Contract):
    source: Literal["customer_declaration"] = "customer_declaration"
    intent: Intent


class PendingOperation(Contract):
    pending_id: Text = Field(default_factory=lambda: str(uuid4()))
    declarations: DeclaredFacts
    requested_fields: Annotated[tuple[Text, ...], Field(min_length=1)]
    records: RecordReferences = Field(default_factory=RecordReferences)

    @model_validator(mode="after")
    def allowed_fields(self):
        permitted = set(type(self.declarations.intent).model_fields) - {"type"}
        if not set(self.requested_fields) <= permitted:
            raise ValueError("Pending fields must belong to the intent")
        if len(set(self.requested_fields)) != len(self.requested_fields):
            raise ValueError("Pending fields must be unique")
        return self

    def apply_update(self, update: ClarificationUpdate, *, clock: Clock):
        if update.pending_id != self.pending_id:
            raise ValueError("Unknown pending operation")
        if update.update.type != self.declarations.intent.type:
            raise ValueError("Clarification cannot change operation type")
        supplied = update.update.model_fields_set - {"type"}
        allowed = set(self.requested_fields)
        if "payment_method" in allowed and "payment_method" in supplied:
            # "No crédito em 6x" answers both facts at once.
            allowed.add("installments")
        if not supplied or not supplied <= allowed:
            raise ValueError("Clarification contains unrequested fields")
        # JSON serialization preserves decimal-string budgets across revalidation.
        merged = self.declarations.intent.model_dump(mode="json")
        patch = update.update.model_dump(mode="json", exclude_unset=True)
        for name, value in patch.items():
            if name in {"condition", "destination"} and isinstance(value, dict):
                merged[name] = {**(merged.get(name) or {}), **value}
            else:
                merged[name] = value
        validated = type(self.declarations.intent).model_validate(
            merged, context={"today": store_today(clock)}
        )
        remaining = tuple(
            name
            for name in self.requested_fields
            if name not in supplied or getattr(validated, name) is None
        )
        # The controller re-evaluates remaining requirements; no quote is cached here.
        return DeclaredFacts(intent=validated), remaining, RecordReferences()


class SessionState(Contract):
    simulated_customer_id: PositiveInt | None = None
    history: Annotated[
        tuple[ConversationMessage, ...], Field(max_length=MAX_HISTORY)
    ] = ()
    displayed_product_ids: tuple[PositiveInt, ...] = ()
    selected_product_id: PositiveInt | None = None
    selected_order_id: PositiveInt | None = None
    pending: Annotated[tuple[PendingOperation, ...], Field(max_length=MAX_PENDING)] = ()

    @model_validator(mode="after")
    def validate_references(self):
        if (
            self.selected_product_id is not None
            and self.selected_product_id not in self.displayed_product_ids
        ):
            raise ValueError("Selected product must belong to the displayed list")
        if len(set(self.displayed_product_ids)) != len(self.displayed_product_ids):
            raise ValueError("Displayed products must be unique")
        if len({item.pending_id for item in self.pending}) != len(self.pending):
            raise ValueError("Pending operation IDs must be unique")
        return self

    def append_message(self, message: ConversationMessage):
        fields = {name: getattr(self, name) for name in type(self).model_fields}
        fields["history"] = (*self.history, message)[-MAX_HISTORY:]
        return type(self)(**fields)


def create_session(snapshot: Snapshot, customer_id: int | None = None) -> SessionState:
    """Startup-only simulated identity; this is not production authentication."""
    if customer_id is not None and (
        type(customer_id) is not int or customer_id not in snapshot.customers
    ):
        raise ValueError("Unknown simulated customer")
    return SessionState(simulated_customer_id=customer_id)
