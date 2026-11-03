"""Sequential catalog controller; provider proposals never own execution state."""

import logging
import re
from dataclasses import dataclass

from pydantic import ValidationError

from .catalog import quote_product, search_catalog
from .composer import compose
from .contracts.common import MAX_MESSAGE_LENGTH
from .contracts.dates import Clock, store_today
from .contracts.intents import (
    ClarificationUpdate,
    OrderStatus,
    PaymentOptions,
    ProductSearch,
    ProposalError,
    RequestTooBroadError,
)
from .contracts.results import (
    RESULT_ADAPTER,
    OperationResult,
    OrderData,
    OrderStatusResult,
    PaymentOptionsResult,
)
from .contracts.session import (
    ConversationMessage,
    DeclaredFacts,
    PendingOperation,
    RecordReferences,
    SessionState,
    create_session,
)
from .data.records import Snapshot
from .providers.base import (
    IntentProvider,
    PendingHint,
    ProviderError,
    ProviderRequest,
)
from .providers.extraction import extract_proposal

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnResponse:
    text: str
    results: tuple[OperationResult, ...] = ()


def _state(state, **changes):
    fields = {key: getattr(state, key) for key in type(state).model_fields}
    return SessionState(**(fields | changes))


def _result(operation, status, reason, missing=()):
    return RESULT_ADAPTER.validate_python(
        dict(
            operation=operation,
            status=status,
            reason_code=reason,
            missing_fields=missing,
        )
    )


class Controller:
    def __init__(
        self,
        snapshot: Snapshot,
        provider: IntentProvider,
        *,
        clock: Clock,
        customer_id: int | None = None,
    ):
        store_today(clock)
        self.snapshot = snapshot
        self.provider = provider
        self.clock = clock
        self.session = create_session(snapshot, customer_id)
        self._typed_order_numbers = set()

    def handle(self, message: str) -> TurnResponse:
        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > MAX_MESSAGE_LENGTH
        ):
            return TurnResponse("Informe uma mensagem com 1 a 4.000 caracteres.")
        message = message.strip()
        if message == "/cancelar":
            self.session = _state(self.session, pending=())
            return self._finish(
                message,
                "Consultas pendentes canceladas; nenhuma transação foi realizada.",
            )
        request = ProviderRequest(
            message=message,
            history=self.session.history,
            displayed_product_names=tuple(
                self.snapshot.products[i].name
                for i in self.session.displayed_product_ids
            ),
            pending=tuple(
                PendingHint(
                    pending_id=p.pending_id,
                    operation=p.declarations.intent.type,
                    requested_fields=p.requested_fields,
                )
                for p in self.session.pending
            ),
        )
        try:
            proposal = extract_proposal(self.provider, request, clock=self.clock)
        except RequestTooBroadError:
            return self._finish(message, "Faça até cinco pedidos por mensagem.")
        except (ProposalError, ProviderError) as error:
            LOGGER.warning("Extraction failed: %s", type(error).__name__)
            return self._finish(
                message, "Não consegui interpretar sua mensagem. Tente novamente."
            )

        prior = None
        if isinstance(proposal, ClarificationUpdate):
            prior = next(
                (
                    p
                    for p in self.session.pending
                    if p.pending_id == proposal.pending_id
                ),
                None,
            )
            try:
                if prior is None:
                    raise ValueError("Unknown pending operation")
                declarations, _, _ = prior.apply_update(proposal, clock=self.clock)
            except ValueError:
                return self._finish(
                    message,
                    "Não consegui aplicar essa correção. Responda aos dados solicitados ou use /cancelar.",
                )
            intents = [declarations.intent]
            pending = list(self.session.pending)
            pending.remove(prior)
        else:
            # A new complete turn replaces prior unfinished requests. Updates target
            # existing pending work explicitly; neither form can change identity.
            intents = proposal.intents
            pending = []

        # A model may copy an order number from history; only ASCII digits typed in
        # the current message, excluding money amounts, can identify an order. This
        # is an extraction-quality filter; authorization is enforced in _order.
        order_text = re.sub(r"R\$\s*[0-9.,]+|[0-9][0-9.]*,[0-9]{2}\b", " ", message)
        typed_numbers = {int(n) for n in re.findall(r"[0-9]+", order_text)}
        self._typed_order_numbers = typed_numbers
        intents = [
            intent.model_copy(update={"order_id": None})
            if isinstance(intent, OrderStatus)
            and intent.order_id not in typed_numbers | {None}
            else intent
            for intent in intents
        ]
        results = []
        shown = []
        selected = self.session.selected_product_id
        selected_order = self.session.selected_order_id
        original_display = self.session.displayed_product_ids
        for intent in intents:
            pinned = None
            if prior is None:
                # Uses the selection current at this point of the turn, so a search
                # earlier in the same turn prevents inheriting another product's facts.
                intent = self._carry_over(intent, selected)
            execution_intent = intent
            if prior and isinstance(intent, PaymentOptions):
                if "product_reference" not in proposal.update.model_fields_set:
                    pinned = prior.records.product_id
                    if "product_reference" in prior.requested_fields:
                        # An unrelated successful search must not answer a missing
                        # selection implicitly during a partial clarification.
                        execution_intent = intent.model_copy(
                            update={"product_reference": None}
                        )
            try:
                outcome, choices, resolved = self._execute(
                    execution_intent, selected, original_display, pinned
                )
            except (ArithmeticError, KeyError, ValidationError) as error:
                # No raw exception text: validators and source records may contain data.
                LOGGER.warning(
                    "Operation failed: %s %s", intent.type, type(error).__name__
                )
                outcome = _result(intent.type, "error", "OPERATION_FAILED")
                choices, resolved = None, None
            if isinstance(intent, ProductSearch):
                # A failed or ambiguous new search must never reuse a stale selection.
                selected = None
            elif isinstance(intent, PaymentOptions) and resolved is None:
                selected = None
            if choices is not None:
                if choices is not outcome:
                    results.append(choices)
                ids = tuple(q.product_id for q in choices.data.products)
                shown.extend(i for i in ids if i not in shown)
                selected = ids[0] if choices.data.total_matches == 1 else None
            if resolved is not None:
                selected = resolved
            if (
                isinstance(outcome, PaymentOptionsResult)
                and outcome.status == "success"
            ):
                if outcome.data.product_id not in shown:
                    shown.append(outcome.data.product_id)
            if isinstance(outcome, OrderStatusResult):
                # Only a successful, authorized lookup may become the order in focus.
                selected_order = (
                    outcome.data.order_id if outcome.status == "success" else None
                )
            results.append(outcome)
            if outcome.status == "needs_information":
                fields = dict(
                    declarations=DeclaredFacts(intent=intent),
                    requested_fields=outcome.missing_fields,
                    records=RecordReferences(product_id=resolved),
                )
                if prior:
                    fields["pending_id"] = prior.pending_id
                item = PendingOperation(**fields)
                if prior:
                    pending.insert(0, item)
                else:
                    pending.append(item)
        # Each displayed number is global within the response, including independent
        # searches. Incoming ordinals always use the list actually seen last turn.
        displayed = tuple(shown) if shown else original_display
        if selected not in displayed:
            selected = None
        self.session = _state(
            self.session,
            displayed_product_ids=displayed,
            selected_product_id=selected,
            selected_order_id=selected_order,
            pending=tuple(pending),
        )
        text = compose(results, displayed, pending)
        return self._finish(message, text, tuple(results))

    def _finish(self, message, text, results=()):
        self.session = self.session.append_message(
            ConversationMessage(role="user", content=message)
        )
        # Keep bounded context without truncating operational output shown to the user.
        history_text = (
            text
            if len(text) <= MAX_MESSAGE_LENGTH
            else "Resposta extensa de catálogo exibida; use os nomes e posições da lista atual."
        )
        self.session = self.session.append_message(
            ConversationMessage(role="assistant", content=history_text)
        )
        return TurnResponse(text, results)

    def _execute(self, intent, selected, original_display, pinned):
        if isinstance(intent, ProductSearch):
            result = search_catalog(self.snapshot, intent)
            return result, result if result.status == "success" else None, None
        if isinstance(intent, PaymentOptions):
            return self._payment(intent, selected, original_display, pinned)
        if isinstance(intent, OrderStatus):
            return self._order(intent), None, None
        return (
            _result(intent.type, "unavailable", "OPERATION_NOT_SUPPORTED"),
            None,
            None,
        )

    def _carry_over(self, intent, selected):
        """Keep facts already declared for the same pending quote.

        Small models often answer a clarification ("no PIX") with a new quote for the
        selected product instead of a pending update. Only facts the customer already
        declared for that same resolved product are reused; nothing is invented.
        """
        if not isinstance(intent, PaymentOptions):
            return intent
        reference = intent.product_reference
        if reference is not None and reference.kind != "selected":
            return intent
        prior = next(
            (
                p
                for p in self.session.pending
                if isinstance(p.declarations.intent, PaymentOptions)
                and p.records.product_id is not None
                and p.records.product_id == selected
            ),
            None,
        )
        if prior is None:
            return intent
        declared = prior.declarations.intent
        changes = {}
        if reference is None:
            changes["product_reference"] = {"kind": "selected"}
        if intent.quantity is None and declared.quantity is not None:
            changes["quantity"] = declared.quantity
        if (
            intent.payment_method is None
            and intent.installments is None
            and declared.payment_method is not None
        ):
            changes["payment_method"] = declared.payment_method
            changes["installments"] = declared.installments
        if not changes:
            return intent
        return PaymentOptions.model_validate(intent.model_dump() | changes)

    def _order(self, intent):
        customer_id = self.session.simulated_customer_id
        if customer_id is None:
            # Without a startup identity, no order record is consulted at all.
            return _result(intent.type, "unauthorized", "ORDER_ACCESS_DENIED")
        order_id = intent.order_id
        if order_id is None and not self._typed_order_numbers:
            # Reuse the focus only when the customer typed no other number; a
            # discarded or missing extraction must not show a different order.
            order_id = self.session.selected_order_id
        if order_id is None:
            return _result(
                intent.type, "needs_information", "ORDER_ID_MISSING", ("order_id",)
            )
        order = self.snapshot.orders.get(order_id)
        if order is None or order.customer_id != customer_id:
            # Foreign and nonexistent orders are indistinguishable externally.
            return _result(intent.type, "not_found", "ORDER_NOT_ACCESSIBLE")
        return OrderStatusResult(
            status="success",
            data=OrderData(
                order_id=order.order_id,
                status=order.status,
                recorded_total_brl=order.total_brl,
                tracking_code=order.tracking_code,
                estimated_delivery=order.estimated_delivery,
            ),
        )

    def _payment(self, intent, selected, original_display, pinned):
        reference = intent.product_reference
        resolved, choices = pinned, None
        if resolved is None and reference is not None:
            if reference.kind == "ordinal":
                if reference.ordinal <= len(original_display):
                    resolved = original_display[reference.ordinal - 1]
            elif reference.kind == "selected":
                resolved = selected
            else:
                found = search_catalog(
                    self.snapshot,
                    ProductSearch(type="product_search", query=reference.query),
                )
                if found.status != "success":
                    return (
                        _result(
                            "payment_options",
                            found.status,
                            found.reason_code,
                            found.missing_fields,
                        ),
                        None,
                        None,
                    )
                choices = found
                if found.data.total_matches == 1:
                    resolved = found.data.products[0].product_id
        if resolved is not None and resolved not in self.snapshot.products:
            resolved = None
        missing = []
        if resolved is None:
            missing.append("product_reference")
        if intent.quantity is None:
            missing.append("quantity")
        if intent.payment_method is None:
            missing.append("payment_method")
        if missing:
            return (
                _result(
                    "payment_options",
                    "needs_information",
                    "QUOTE_FACTS_MISSING",
                    tuple(missing),
                ),
                choices,
                resolved,
            )
        quote = quote_product(
            self.snapshot,
            resolved,
            ProductSearch(
                type="product_search",
                quantity=intent.quantity,
                payment_method=intent.payment_method,
                installments=intent.installments,
            ),
        )
        if quote.status != "success":
            return (
                PaymentOptionsResult(
                    status=quote.status,
                    reason_code=quote.reason_code,
                    missing_fields=quote.missing_fields,
                    policy_references=quote.policy_references,
                ),
                choices,
                resolved,
            )
        return (
            PaymentOptionsResult(
                status="success",
                data=quote.data.products[0],
                policy_references=quote.policy_references,
            ),
            choices,
            resolved,
        )
