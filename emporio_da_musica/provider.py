"""Provider-independent extraction boundary; no real provider or dispatch yet."""

from typing import Annotated, Protocol

from pydantic import Field

from .contracts.common import MAX_HISTORY, MAX_PENDING, Contract, Operation, Text
from .contracts.dates import Clock
from .contracts.intents import (
    Proposal,
    ProposalError,
    RequestTooBroadError,
    parse_proposal,
)
from .contracts.session import ConversationMessage


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


class ProviderError(RuntimeError):
    """Provider adapters translate connection/timeout failures to this exception."""


def extract_proposal(
    provider: IntentProvider, request: ProviderRequest, *, clock: Clock
) -> Proposal:
    """Allow one schema repair, without exposing validation details to the provider."""
    try:
        return parse_proposal(provider.propose(request), clock=clock)
    except RequestTooBroadError:
        raise
    except ProposalError:
        repaired = ProviderRequest(
            message=request.message,
            history=request.history,
            displayed_product_names=request.displayed_product_names,
            pending=request.pending,
            repair_requested=True,
        )
        return parse_proposal(provider.propose(repaired), clock=clock)
