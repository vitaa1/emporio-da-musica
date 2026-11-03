"""Provider-neutral request contracts, protocol, and errors."""

from typing import Annotated, Protocol

from pydantic import Field

from ..contracts.common import MAX_HISTORY, MAX_PENDING, Contract, Operation, Text
from ..contracts.session import ConversationMessage


class PendingHint(Contract):
    pending_id: Text
    operation: Operation
    requested_fields: tuple[Text, ...]


class ProviderRequest(Contract):
    message: Text
    history: Annotated[
        tuple[ConversationMessage, ...], Field(max_length=MAX_HISTORY)
    ] = ()
    displayed_product_names: tuple[Text, ...] = ()
    pending: Annotated[tuple[PendingHint, ...], Field(max_length=MAX_PENDING)] = ()
    repair_requested: bool = False


class IntentProvider(Protocol):
    def propose(self, request: ProviderRequest) -> str:
        """Return raw JSON; implementations must not execute domain operations."""
        ...


class PolicyRequest(Contract):
    """Only the general question; no history, identity, or session state."""

    question: Text


class PolicyProvider(Protocol):
    def explain(self, request: PolicyRequest) -> str:
        """Return raw JSON matching PolicyData; validated by the caller."""
        ...


class ProviderError(RuntimeError):
    """Provider adapters translate connection/timeout failures to this exception."""


class ProviderConnectionError(ProviderError):
    """The model server could not be reached or did not answer in time."""
