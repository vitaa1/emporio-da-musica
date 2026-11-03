"""Sequential catalog controller; provider proposals never own execution state."""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from .catalog import normalize, quote_product, search_catalog
from .composer import BUDGET_IGNORED, CITY_ASSUMED, QUOTE_FACTS_REUSED, compose
from .contracts.common import MAX_MESSAGE_LENGTH
from .contracts.dates import Clock, store_today
from .contracts.intents import (
    ClarificationUpdate,
    Complaint,
    IntentTurn,
    OrderStatus,
    OutOfScope,
    PaymentOptions,
    PolicyQuestion,
    ProductSearch,
    ProposalError,
    RequestTooBroadError,
    ReturnAssessment,
    ShippingQuote,
    SmallTalk,
)
from .contracts.results import (
    RESULT_ADAPTER,
    ComplaintData,
    ComplaintResult,
    OperationResult,
    OrderData,
    OrderStatusResult,
    OutOfScopeData,
    OutOfScopeResult,
    PaymentOptionsResult,
    PolicyData,
    PolicyQuestionResult,
    ReturnAssessmentResult,
    ShippingData,
    ShippingQuoteResult,
    SmallTalkData,
    SmallTalkResult,
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
from .providers.policy import (
    ContactConflict,
    NotCovered,
    PolicyAnswerError,
    explain_policy,
)
from .returns import REFERENCES, assess_return, required_fields

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnResponse:
    text: str
    results: tuple[OperationResult, ...] = ()


def _state(state, **changes):
    fields = {key: getattr(state, key) for key in type(state).model_fields}
    return SessionState(**(fields | changes))


# The address is a fixed fact (manual §1.2). The small policy model sometimes
# reports it as uncovered, so an uncovered or failed answer falls back to this
# text, but only when the whole question is a store-address request: mixed
# questions, delivery addresses, and order locations keep their normal outcome.
_ADDRESS_PHRASES = (
    r"(?:qual (?:e )?)?o endereco(?: da loja| de voces| de vcs)?",
    r"(?:qual (?:e )?a )?(?:rua|localizacao|cep) da loja",
    r"onde (?:fica|e|esta) a loja(?: de voces)?",
    r"onde voces (?:ficam|estao)",
    r"voces (?:ficam|estao) onde",
    r"como (?:chego|chegar|faco (?:pra|para) chegar) "
    r"(?:ai|na loja|a loja|ate a loja|ate voces)",
)
ADDRESS_ONLY = re.compile(
    r"^\W*(?:(?:oi|ola|bom dia|boa tarde|boa noite)\W+)?(?:"
    + "|".join(_ADDRESS_PHRASES)
    + r")(?:\W+(?:por favor|pf))?\W*$"
)
STORE_ADDRESS = (
    "A loja fica na Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333."
)

# Accessories named in manual §§1 and 7.1. Ambiguous words need context: an
# instrument "de 7 cordas" or "cordas orquestrais" (a store category), "Cabo
# Frio", "capa do livro", or a drum "pedal de bateria" are not accessory requests.
ACCESSORY_WORDS = re.compile(
    r"\bacessorios?\b|\bencordoamentos?\b|\bpalhetas?\b|\bpedaleiras?\b"
    r"|\bamplificador(?:es)?\b|\bpedais\b(?! de bateria)"
    r"|\bpedal (?:de efeito|para guitarra|pra guitarra)\b"
    r"|(?<![0-9] )\bcordas?\b(?! orquestra)"
    r"|\b(?:cabos|capas|cases)\b(?! d[oa]s? )"
    r"|\b(?:cabo|capa|case) (?:de|para|pra|p10|p2)\b"
)

QUOTES = (PaymentOptions, ShippingQuote)
# Only PIX changes a price, so only PIX needs evidence in the current message; a
# copied or misread PIX would apply an undeclared discount. Parsing Portuguese fully
# is not attempted: any doubt (negation, another method) fails closed and asks.
_COUNT = r"(?:[0-9]+|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)"
PAYMENT_MENTION = re.compile(
    r"\b(?:pix|cartao|debito|debit|credito|credit|boleto|dinheiro|parcel\w*|vezes|"
    r"[0-9]+ ?x|a vista|a prazo|sem juros|combin\w*|meio a meio|dividi\w*)\b"
)
_NOT_PIX = re.compile(
    r"\b(?:nao|sem|nem|vez de|cartao|debito|debit|credito|credit|boleto|dinheiro|"
    r"parcel\w*|vezes|[0-9]+ ?x|combin\w*|meio a meio|dividi\w*)\b"
)


def pix_declared(message):
    """PIX named with no negation and no other payment term nearby in the message."""
    text = normalize(message)
    return re.search(r"\bpix\b", text) is not None and not _NOT_PIX.search(text)


# A product reference made only of payment words ("débito", "no cartão") was
# invented from the payment method; it never names a product.
_PAYMENT_WORD = (
    r"(?:no|na|em|de|a|com|pelo|pela|via|vista|prazo|sem|juros|meio|pagamento|"
    r"combinado|cartao|credito|debito|pix|boleto|parcelado|parcelas?|vezes|dinheiro|"
    rf"{_COUNT}x?)"
)
PAYMENT_ONLY = re.compile(rf"^{_PAYMENT_WORD}(?:\s+{_PAYMENT_WORD})*\W*$")
FREE_FREIGHT_ABOVE = Decimal("500")  # Supplied manual §5.1.
LOCAL_FREIGHT = Decimal("35")
LOCAL_CITY = "campo grande"

RECEIPT_WORDS = re.compile(r"\b(hoje|ontem|anteontem)\b")
MONTHS = (
    "janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|"
    "outubro|novembro|dezembro"
)
# Dates are not order numbers: "recebi dia 5", "05/11", "5 de novembro".
DATE_TEXT = re.compile(
    r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b|\b[0-9]{1,2}/[0-9]{1,2}(?:/[0-9]{2,4})?\b"
    rf"|\bdia\s+[0-9]{{1,2}}\b|\b[0-9]{{1,2}}\s+de\s+(?:{MONTHS})\b",
    re.IGNORECASE,
)

CONTACT_REQUEST = re.compile(
    r"\b(telefone|fone|whats\w*|zap|e-?mail|contato|ligar|numero da loja)\b"
)


def _typed_amounts(message):
    """Decimal amounts typed in a message: 1000, 1.000, 1.000,50, 1000.00, 2 mil."""
    amounts = set()
    for token, thousand in re.findall(
        r"([0-9][0-9.,]*)(\s*mil\b)?", message, flags=re.IGNORECASE
    ):
        token = token.rstrip(".,")
        if re.fullmatch(r"[0-9]{1,3}(\.[0-9]{3})+(,[0-9]{1,2})?", token):
            token = token.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"[0-9]+,[0-9]{1,2}", token):
            token = token.replace(",", ".")
        elif not re.fullmatch(r"[0-9]+(\.[0-9]{1,2})?", token):
            continue
        value = Decimal(token)
        amounts.add(value * 1000 if thousand else value)
    if re.search(r"(?<![0-9\s])\s*\bmil\b", message, flags=re.IGNORECASE):
        amounts.add(Decimal(1000))
    return amounts


def _payment_only(reference):
    return (
        reference is not None
        and reference.kind == "query"
        and PAYMENT_ONLY.match(normalize(reference.query)) is not None
        # A bare number may be a model code ("o 310"), not a payment term.
        and PAYMENT_MENTION.search(normalize(reference.query)) is not None
    )


def _clean_update(proposal, prior, message):
    """Drop model inventions from an update that also answers something else.

    A payment-word product reference and an unrequested, untyped payment method
    would otherwise reject the customer's valid answer. An update left with no
    other field is returned unchanged for the normal validation.
    """
    update = proposal.update
    if not isinstance(update, QUOTES):
        return proposal
    fields = update.model_dump(mode="json", exclude_unset=True)
    if _payment_only(update.product_reference):
        fields.pop("product_reference")
    requested = prior.requested_fields if prior else ()
    if (
        "payment_method" in fields
        and "payment_method" not in requested
        and not PAYMENT_MENTION.search(normalize(message))
    ):
        fields.pop("payment_method")
        fields.pop("installments", None)
    if set(fields) <= {"type"} or len(fields) == len(update.model_fields_set):
        return proposal
    return ClarificationUpdate(
        pending_id=proposal.pending_id, update=type(update).model_validate(fields)
    )


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
        self._message = ""
        # Facts of the last successful quote: (product ID, executed intent).
        self._last_quote = None
        self._reused_quote = False
        self._intent_count = 1

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
            # Cancelling also forgets facts of the last completed quote.
            self._last_quote = None
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
        kept = []
        if isinstance(proposal, ClarificationUpdate):
            prior = next(
                (
                    p
                    for p in self.session.pending
                    if p.pending_id == proposal.pending_id
                ),
                None,
            )
            proposal = _clean_update(proposal, prior, message)
            try:
                if prior is None:
                    raise ValueError("Unknown pending operation")
                declarations, _, _ = prior.apply_update(proposal, clock=self.clock)
            except ValueError:
                if not (
                    prior
                    and isinstance(prior.declarations.intent, ReturnAssessment)
                    and isinstance(proposal.update, ReturnAssessment)
                ):
                    return self._finish(
                        message,
                        "Não consegui aplicar essa correção. Responda aos dados solicitados ou use /cancelar.",
                    )
                # Return facts are often answered together ("online, recebi
                # ontem"); treat the update as a new turn merged with the pending
                # declarations instead of rejecting the extra facts.
                proposal = IntentTurn(intents=[proposal.update])
                # Other pending operations were not addressed and stay waiting.
                kept = [p for p in self.session.pending if p is not prior]
                prior = None
        if prior is not None:
            intents = [declarations.intent]
            pending = list(self.session.pending)
            pending.remove(prior)
        else:
            # A new complete turn replaces prior unfinished requests. Updates target
            # existing pending work explicitly; neither form can change identity.
            intents = proposal.intents
            pending = kept

        # A model may copy an order number from history; only ASCII digits typed in
        # the current message, excluding money amounts, can identify an order. This
        # is an extraction-quality filter; authorization is enforced in _order.
        order_text = re.sub(r"R\$\s*[0-9.,]+|[0-9][0-9.]*,[0-9]{2}\b", " ", message)
        order_text = DATE_TEXT.sub(" ", order_text)
        typed_numbers = {int(n) for n in re.findall(r"[0-9]+", order_text)}
        self._typed_order_numbers = typed_numbers
        self._message = message
        self._intent_count = len(intents)
        # Budgets and model-written search terms follow the same rule: values copied
        # from history or invented by the model must not hide or replace products.
        typed_amounts = _typed_amounts(message)
        notes = []
        checked = []
        for intent in intents:
            if isinstance(intent, ProductSearch):
                if (
                    intent.max_price_brl is not None
                    and intent.max_price_brl not in typed_amounts
                ):
                    intent = intent.model_copy(update={"max_price_brl": None})
                    notes.append(BUDGET_IGNORED)
                if (
                    intent.query
                    and intent.category
                    and normalize(intent.query) not in normalize(message)
                ):
                    # e.g. "viola" invented for "violões": keep the typed category.
                    intent = intent.model_copy(update={"query": None})
            if isinstance(intent, QUOTES) and _payment_only(intent.product_reference):
                intent = intent.model_copy(update={"product_reference": None})
            checked.append(intent)
        intents = checked
        # Facts carried in a merged clarification were checked when first supplied;
        # only values supplied by this proposal must appear in this message.
        supplied = proposal.update.model_fields_set if prior else None
        intents = [
            self._typed_payment(
                self._typed_facts(intent, supplied, typed_numbers), supplied
            )
            for intent in intents
        ]
        if supplied is None or "payment_method" in supplied:
            # Methods merged from earlier declarations were checked when supplied.
            intents = self._one_method_per_mention(intents)
        results = []
        shown = []
        selected = self.session.selected_product_id
        selected_order = self.session.selected_order_id
        original_display = self.session.displayed_product_ids
        listed = False
        for intent in intents:
            pinned = None
            if prior is None:
                # Uses the selection current at this point of the turn, so a search
                # earlier in the same turn prevents inheriting another product's facts.
                self._reused_quote = False
                intent = self._carry_over(intent, selected)
                if self._reused_quote:
                    notes.append(QUOTE_FACTS_REUSED)
            execution_intent = intent
            if prior and isinstance(intent, QUOTES):
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
                # A failed or ambiguous new search must never reuse a stale selection
                # or the facts of an earlier quote.
                selected = None
                self._last_quote = None
            elif (
                isinstance(intent, QUOTES)
                and resolved is None
                and intent.product_reference is not None
            ):
                # Only a reference that failed to resolve drops the selection. A
                # quote that named no product still asks for it, but keeps the
                # selection so a later "esse" refers to the same product.
                selected = None
            if choices is not None:
                # A unique name match quoted successfully is already shown by the
                # quote; the search line is kept only for choices or failures.
                unique_quote = (
                    choices.data.total_matches == 1
                    and resolved == choices.data.products[0].product_id
                    and outcome.status == "success"
                    and isinstance(outcome, (PaymentOptionsResult, ShippingQuoteResult))
                )
                if choices is not outcome and not unique_quote:
                    results.append(choices)
                if choices is outcome or not unique_quote:
                    listed = True
                ids = tuple(q.product_id for q in choices.data.products)
                shown.extend(i for i in ids if i not in shown)
                selected = ids[0] if choices.data.total_matches == 1 else None
            if resolved is not None:
                selected = resolved
            if isinstance(outcome, (PaymentOptionsResult, ShippingQuoteResult)):
                # Only a successful, available quote is remembered; any other
                # outcome forgets the earlier facts instead of reviving them later.
                self._last_quote = None
            if (
                isinstance(outcome, (PaymentOptionsResult, ShippingQuoteResult))
                and outcome.status == "success"
            ):
                quoted = (
                    outcome.data.quote
                    if isinstance(outcome.data, ShippingData)
                    else outcome.data
                )
                if quoted.product_id not in shown:
                    shown.append(quoted.product_id)
                if quoted.availability == "available":
                    self._last_quote = (quoted.product_id, intent)
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
        # Quoting items of the list seen last turn keeps that list, so "o segundo"
        # still works; a new list replaces it only when one was actually shown.
        keep_list = not listed and all(i in original_display for i in shown)
        displayed = tuple(shown) if shown and not keep_list else original_display
        if selected not in displayed:
            selected = None
        self.session = _state(
            self.session,
            displayed_product_ids=displayed,
            selected_product_id=selected,
            selected_order_id=selected_order,
            pending=tuple(pending),
        )
        results = self._contact_notice(results, intents)
        text = compose(results, displayed, pending, notes=tuple(dict.fromkeys(notes)))
        return self._finish(message, text, tuple(results))

    def _finish(self, message, text, results=()):
        self.session = self.session.append_message(
            ConversationMessage(role="user", content=message)
        )
        # Keep bounded context without truncating operational output shown to the user.
        history_text = (
            text
            if len(text) <= MAX_MESSAGE_LENGTH
            else "Resposta extensa exibida; use os nomes e posições da lista atual."
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
        if isinstance(intent, ShippingQuote):
            return self._shipping(intent, selected, original_display, pinned)
        if isinstance(intent, OrderStatus):
            return self._order(intent), None, None
        if isinstance(intent, ReturnAssessment):
            return self._return(intent), None, None
        if isinstance(intent, PolicyQuestion):
            return self._policy(intent), None, None
        if isinstance(intent, OutOfScope):
            return self._out_of_scope(intent.topic), None, None
        if isinstance(intent, Complaint):
            return ComplaintResult(status="success", data=ComplaintData()), None, None
        if isinstance(intent, SmallTalk):
            data = SmallTalkData(template=intent.kind or "greeting")
            return SmallTalkResult(status="success", data=data), None, None
        return (
            _result(intent.type, "unavailable", "OPERATION_NOT_SUPPORTED"),
            None,
            None,
        )

    def _typed_facts(self, intent, supplied, typed_numbers):
        """Drop order numbers and receipt dates the customer did not type now."""
        if not isinstance(intent, (OrderStatus, ReturnAssessment)):
            return intent
        changes = {}
        if (
            (supplied is None or "order_id" in supplied)
            and intent.order_id is not None
            and intent.order_id not in typed_numbers
        ):
            changes["order_id"] = None
        if (
            isinstance(intent, ReturnAssessment)
            and (supplied is None or "received_at" in supplied)
            and intent.received_at is not None
            # The resolved day must be typed now (e.g. "dia 5", "05/11") unless a
            # relative word was used; any unrelated digit is not enough.
            and intent.received_at.day
            not in {int(n) for n in re.findall(r"[0-9]+", self._message)}
            and not RECEIPT_WORDS.search(normalize(self._message))
        ):
            changes["received_at"] = None
        return intent.model_copy(update=changes) if changes else intent

    def _typed_payment(self, intent, supplied):
        """Drop a PIX, and thus its discount, not declared in this message."""
        if (
            not isinstance(intent, (ProductSearch, *QUOTES))
            or intent.payment_method != "pix"
            or (supplied is not None and "payment_method" not in supplied)
            or pix_declared(self._message)
        ):
            return intent
        return intent.model_copy(update={"payment_method": None, "installments": None})

    def _one_method_per_mention(self, intents):
        """One PIX mention discounts the first request and those depending on it."""
        mentions = len(re.findall(r"\bpix\b", normalize(self._message)))
        used = 0
        result = []
        for intent in intents:
            if getattr(intent, "payment_method", None) == "pix":
                reference = getattr(intent, "product_reference", None)
                if reference is None or reference.kind != "selected":
                    used += 1
                if used > mentions:
                    intent = intent.model_copy(
                        update={"payment_method": None, "installments": None}
                    )
            result.append(intent)
        return result

    def _names_other_product(self, selected):
        """Whether the message has a name token exclusive to other catalog products."""

        def tokens(text):
            return set(
                re.findall(r"\w{4,}|\w*[a-z]\w*[0-9]\w*|\w*[0-9]\w*[a-z]\w*", text)
            )

        words = tokens(normalize(self._message))
        own = tokens(normalize(self.snapshot.products[selected].name))
        return any(
            words & (tokens(normalize(product.name)) - own)
            for product in self.snapshot.products.values()
        )

    def _same_as_selected(self, reference, selected, original_display):
        """Whether an ordinal or unique name points to the selected product."""
        if selected is None:
            return False
        if reference.kind == "ordinal":
            return (
                reference.ordinal <= len(original_display)
                and original_display[reference.ordinal - 1] == selected
            )
        found = search_catalog(
            self.snapshot, ProductSearch(type="product_search", query=reference.query)
        )
        return (
            found.status == "success"
            and found.data.total_matches == 1
            and found.data.products[0].product_id == selected
        )

    def _carry_return(self, intent):
        """Reuse facts declared for a pending return answered as a new turn."""
        prior = next(
            (
                p.declarations.intent
                for p in self.session.pending
                if isinstance(p.declarations.intent, ReturnAssessment)
                and intent.reason in (None, p.declarations.intent.reason)
                # Facts declared about one order never transfer to another.
                and intent.order_id in (None, p.declarations.intent.order_id)
            ),
            None,
        )
        if prior is None:
            return intent
        merged = prior.model_dump(mode="json")
        for name, value in intent.model_dump(mode="json").items():
            if name == "condition" and value and merged.get("condition"):
                merged["condition"] = merged["condition"] | {
                    k: v for k, v in value.items() if v is not None
                }
            elif value is not None:
                merged[name] = value
        try:
            return ReturnAssessment.model_validate(
                merged, context={"today": store_today(self.clock)}
            )
        except ValidationError:
            # Carried facts that no longer validate are dropped, not raised.
            return intent

    def _carry_over(self, intent, selected):
        """Keep facts already declared for the same pending quote.

        Small models often answer a clarification ("no PIX") with a new quote for the
        selected product instead of a pending update. Only facts the customer already
        declared for that same resolved product are reused; nothing is invented.
        """
        if isinstance(intent, ReturnAssessment):
            return self._carry_return(intent)
        if not isinstance(intent, QUOTES):
            return intent
        if selected in self.snapshot.products and self._names_other_product(selected):
            return intent
        reference = intent.product_reference
        if (
            reference is not None
            and reference.kind != "selected"
            and not self._same_as_selected(
                reference, selected, self.session.displayed_product_ids
            )
        ):
            return intent
        prior = next(
            (
                p
                for p in self.session.pending
                # Payment and shipping quotes share product, quantity, and payment
                # facts; only those move between the two intent types.
                if isinstance(p.declarations.intent, QUOTES)
                and p.records.product_id is not None
                and p.records.product_id == selected
            ),
            None,
        )
        if prior is not None:
            declared = prior.declarations.intent
        elif self._last_quote is not None and self._last_quote[0] == selected:
            # "E o frete dele?" after a completed quote: reuse that quote's facts
            # for the same selected product only.
            declared = self._last_quote[1]
        else:
            return intent
        changes = {}
        if reference is None:
            changes["product_reference"] = {"kind": "selected"}
        if intent.quantity is None and declared.quantity is not None:
            changes["quantity"] = declared.quantity
        if (
            intent.payment_method is None
            and intent.installments is None
            and declared.payment_method is not None
            and not PAYMENT_MENTION.search(normalize(self._message))
        ):
            changes["payment_method"] = declared.payment_method
            changes["installments"] = declared.installments
        if (
            isinstance(intent, ShippingQuote)
            and isinstance(declared, ShippingQuote)
            and intent.destination is None
            and declared.destination is not None
        ):
            changes["destination"] = declared.destination.model_dump()
        if not changes:
            return intent
        if set(changes) - {"product_reference"}:
            # Reused facts are announced so a discount is never applied silently.
            self._reused_quote = True
        return type(intent).model_validate(intent.model_dump() | changes)

    def _policy(self, intent):
        if not hasattr(self.provider, "explain"):
            return _result(intent.type, "unavailable", "POLICY_MODEL_UNAVAILABLE")
        # Only text from the customer's current message is sent: the model-isolated
        # question when it is literally part of that message, otherwise the whole
        # message. History, identity, and facts from earlier turns are never sent.
        question = self._message
        if intent.question and normalize(intent.question).strip(" ?!.") in normalize(
            self._message
        ):
            question = intent.question
        if CONTACT_REQUEST.search(normalize(question)):
            # The manual lists conflicting contacts; answer deterministically.
            # Only the isolated question counts, so a contact word elsewhere in
            # the message does not hide another policy question. Model answers
            # are still filtered for contacts in providers/policy.py.
            return _result(intent.type, "requires_confirmation", "CONTACT_CONFLICT")
        try:
            data = explain_policy(self.provider, question)
        except NotCovered:
            if ADDRESS_ONLY.match(normalize(question)):
                return self._store_address()
            # Uncovered or unrelated questions get a fixed scope template.
            return self._out_of_scope(None)
        except ContactConflict:
            return _result(intent.type, "requires_confirmation", "CONTACT_CONFLICT")
        except (PolicyAnswerError, ProviderError) as error:
            LOGGER.warning("Policy answer failed: %s", type(error).__name__)
            if ADDRESS_ONLY.match(normalize(question)):
                return self._store_address()
            return _result(intent.type, "error", "POLICY_ANSWER_FAILED")
        return PolicyQuestionResult(
            status="success", data=data, policy_references=data.policy_references
        )

    def _out_of_scope(self, topic):
        """Accessory requests get the store-scope message; other topics a general one."""
        # The model's short topic is checked when present; the message is used
        # only when no topic exists and it holds a single request, so words that
        # belong to another intent in the same turn are not counted.
        if topic:
            text = normalize(topic)
        elif self._intent_count == 1:
            text = normalize(self._message)
        else:
            text = ""
        template = (
            "accessory_redirect" if ACCESSORY_WORDS.search(text) else "scope_redirect"
        )
        return OutOfScopeResult(
            status="success", data=OutOfScopeData(template=template)
        )

    def _contact_notice(self, results, intents):
        """Keep a contact request visible and avoid repeating the address.

        The conflict notice already includes the address, so a fixed address
        fallback is dropped next to it. If the message asks for a contact but the
        model isolated only another question, the notice is added once.
        """
        conflict = any(r.reason_code == "CONTACT_CONFLICT" for r in results)
        if (
            not conflict
            and any(isinstance(i, PolicyQuestion) for i in intents)
            and CONTACT_REQUEST.search(normalize(self._message))
        ):
            results.append(
                _result("policy_question", "requires_confirmation", "CONTACT_CONFLICT")
            )
            conflict = True
        if conflict:
            results = [
                r
                for r in results
                if not (
                    isinstance(r.data, PolicyData) and r.data.answer == STORE_ADDRESS
                )
            ]
        return results

    @staticmethod
    def _store_address():
        data = PolicyData(answer=STORE_ADDRESS, policy_references=("1.2",))
        return PolicyQuestionResult(
            status="success", data=data, policy_references=("1.2",)
        )

    def _return(self, intent):
        if intent.order_id is None and not self._typed_order_numbers:
            # Same focus rule as order lookup; only an authorized lookup sets it.
            focus = self.session.selected_order_id
            if focus is not None:
                intent = intent.model_copy(update={"order_id": focus})
        missing = required_fields(intent)
        if missing:
            reason = intent.reason
            return ReturnAssessmentResult(
                status="needs_information",
                reason_code="RETURN_FACTS_MISSING",
                missing_fields=missing,
                policy_references=(("4",) if reason is None else REFERENCES[reason]),
            )
        order = None
        if intent.order_id is not None:
            customer_id = self.session.simulated_customer_id
            if customer_id is None:
                return _result(intent.type, "unauthorized", "ORDER_ACCESS_DENIED")
            order = self.snapshot.orders.get(intent.order_id)
            if order is None or order.customer_id != customer_id:
                return _result(intent.type, "not_found", "ORDER_NOT_ACCESSIBLE")
        return assess_return(intent, order, store_today(self.clock))

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

    def _shipping(self, intent, selected, original_display, pinned):
        """Local freight only (§5.1); the subtotal follows the payment quote."""
        quote, choices, resolved = self._payment(
            PaymentOptions(
                type="payment_options",
                product_reference=intent.product_reference,
                quantity=intent.quantity,
                payment_method=intent.payment_method,
                installments=intent.installments,
            ),
            selected,
            original_display,
            pinned,
        )
        if quote.status not in ("success", "needs_information"):
            # A failed quote is reported directly; no destination is requested.
            return (
                ShippingQuoteResult(
                    status=quote.status,
                    reason_code=quote.reason_code,
                    policy_references=quote.policy_references,
                ),
                choices,
                resolved,
            )
        if quote.status == "success" and quote.data.availability != "available":
            return (
                _result("shipping_quote", "unavailable", "PRODUCT_NOT_SHIPPABLE"),
                choices,
                resolved,
            )
        city = intent.destination.city if intent.destination else None
        missing = list(quote.missing_fields)
        if city is None:
            missing.append("destination")
        if missing:
            return (
                _result(
                    "shipping_quote",
                    "needs_information",
                    "SHIPPING_FACTS_MISSING",
                    tuple(missing),
                ),
                choices,
                resolved,
            )
        state = intent.destination.state
        postal_code = intent.destination.postal_code
        # Only the declared city is used; a postal code or the customer's record
        # never establishes the delivery region.
        # Without a state, a postal code outside MS (79xxx) contradicts the
        # assumption that "Campo Grande" means Campo Grande/MS.
        foreign_postal = (
            state is None
            and postal_code is not None
            and not postal_code.startswith("79")
        )
        if normalize(city) != LOCAL_CITY or state not in (None, "MS") or foreign_postal:
            return (
                _result(
                    "shipping_quote",
                    "requires_confirmation",
                    "DELIVERY_REGION_UNCONFIRMED",
                ).model_copy(update={"policy_references": ("5", "5.2")}),
                choices,
                resolved,
            )
        subtotal = quote.data.final_total_brl
        if subtotal == FREE_FREIGHT_ABOVE:
            return (
                _result(
                    "shipping_quote", "requires_confirmation", "FREE_FREIGHT_BOUNDARY"
                ).model_copy(update={"policy_references": ("5.1",)}),
                choices,
                resolved,
            )
        assumptions = () if state else (CITY_ASSUMED,)
        return (
            ShippingQuoteResult(
                status="success",
                data=ShippingData(
                    quote=quote.data,
                    subtotal_brl=subtotal,
                    freight_brl=(
                        Decimal("0.00")
                        if subtotal > FREE_FREIGHT_ABOVE
                        else LOCAL_FREIGHT
                    ),
                    destination_city="Campo Grande/MS",
                    assumptions=assumptions,
                ),
                policy_references=("5.1", *quote.policy_references),
            ),
            choices,
            resolved,
        )
