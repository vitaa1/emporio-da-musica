"""Validate extraction output with at most one schema repair."""

from ..contracts.dates import Clock
from ..contracts.intents import (
    Proposal,
    ProposalError,
    RequestTooBroadError,
    parse_proposal,
)
from .base import IntentProvider, ProviderRequest


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
