"""Sequential catalog controller; provider proposals never own execution state."""

import difflib
import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from .catalog import normalize, quote_product, search_catalog
from .composer import (
    BUDGET_IGNORED,
    CITY_ASSUMED,
    QUOTE_FACTS_REUSED,
    SEARCH_FILTER_DROPPED,
    compose,
    render_alternatives,
)
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
    CatalogData,
    CatalogGuide,
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
    ProductSearchResult,
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
    ProviderConnectionError,
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

MODEL_UNAVAILABLE = (
    "O serviço de linguagem está indisponível agora, então não li sua mensagem. "
    "Verifique se o Ollama está em execução e se o endereço (--ollama-url) está "
    "correto."
)
# Typed instrument words, without accents, and the category text each one selects.
INSTRUMENT_CATEGORIES = {
    "violao": "Violões",
    "violoes": "Violões",
    "guitarra": "Guitarras",
    "guitarras": "Guitarras",
    "ukulele": "Ukuleles",
    "ukuleles": "Ukuleles",
    "teclado": "Teclados",
    "teclados": "Teclados",
    "piano": "Pianos",
    "pianos": "Pianos",
    "bateria": "Baterias",
    "baterias": "Baterias",
    "baixo": "Baixos",
    "baixos": "Baixos",
}
MIN_RECOVERED_TERM_LENGTH = 4
MIN_CORRECTABLE_LENGTH = 5
NOT_MISSPELLED = {"musica", "musico"}
MAX_ALTERNATIVES = 3
PURCHASE_WORDS = re.compile(
    r"\b(quero|queria|querendo|comprar|compra|procuro|procurando|preciso|gostaria"
    r"|interesse|interessad[oa])\b"
)
LIST_WORDS = re.compile(
    r"\b(liste|listar|lista|mostre|mostrar|mostra|quais|opcoes|todos|todas|catalogo"
    r"|ver)\b"
)
# Words that make a message a store-policy question even if the model misroutes it.
POLICY_TOPIC = re.compile(
    r"\b(prazo|prazos|devolucao|devolucoes|devolver|troca|trocas|trocar|garantia"
    r"|frete|entrega|pagamento|pagamentos|parcelar|parcelamento|boleto|horario"
    r"|horarios|abre|abrem|fecha|fecham|funciona|funcionam|endereco|acumula|acumular"
    r"|acumulam|desconto|descontos|reembolso)\b"
)
# Families the store's categories mention but the catalog has no product for.
OUTSIDE_CATALOG = re.compile(
    r"\b(violino|violinos|violoncelo|violoncelos|flauta|flautas|clarinete|clarinetes"
    r"|saxofone|saxofones|oboe|oboes|fagote|fagotes|trompete|trompetes|trombone"
    r"|trombones|tuba|tubas|trompa|trompas|harpa|harpas)\b"
)
SELL_QUESTION = re.compile(r"\b(vende|vendem|vendas?|tem|tens|trabalh\w+|possuem)\b")
PROMOTION_WORDS = re.compile(r"\b(promocao|promocoes|oferta|ofertas)\b")
PROMOTION_RULE = re.compile(
    r"\b(acumula|acumular|acumulam|cumulativ[oa]|pix|regra|regras|politica|como funcion\w+)\b"
)
SOCIAL_WORDS = re.compile(
    r"\b(oi|oie|ola|opa|e ai|eai|salve|beleza|como vai|boas|fala|hey|hello|bom dia|boa tarde|boa noite|tudo bem|tudo bom"
    r"|obrigad[oa]|valeu|tchau|ate mais|ate logo|adeus)\b"
)
IDENTITY_QUESTION = re.compile(
    r"\b(quem e voce|quem e vc|quem es|qual (e )?o? ?seu nome|com quem (eu )?falo"
    r"|voce e (um )?(robo|humano|uma pessoa|uma ia))\b"
)
OTHER_METHOD = re.compile(r"\b(pix|boleto|debito)\b")
# After a brand: an unknown next word is a model the promotion must not stand in for.
AFTER_NAME_WORDS = {
    "tem", "tens", "esta", "ta", "em", "com", "no", "na", "de", "do", "da", "ainda",
    "e", "ou", "ficou", "entrou", "promocao", "oferta", "por", "para",
}  # fmt: skip
INSTALLMENT_COUNT_QUESTION = re.compile(
    r"\b(quantas vezes|quantas parcelas|ate quantas)\b"
)
BUDGET_HINT = re.compile(
    r"\b(ate|menos|abaixo|orcamento|reais|mil)\b|r\$|\b[0-9][0-9.,]*\b"
)
BARE_REQUEST_WORDS = {"um", "uma", "o", "a", "de"}
# Leading product-name words that describe the instrument rather than its brand.
GENERIC_NAME_WORDS = {"bateria", "teclado", "sintetizador", "piano", "baixo", "kit"}
MIN_GUIDED_MATCHES = 4
MAX_GUIDE_BRANDS = 6


def _is_broad_request(intent, message):
    """A purchase wish or a bare instrument word, with no filter to apply yet."""
    if (
        intent.query
        or intent.max_price_brl is not None
        or intent.quantity is not None
        or intent.payment_method is not None
    ):
        return False
    text = normalize(message)
    if LIST_WORDS.search(text):
        return False
    words = set(_words(message))
    if PURCHASE_WORDS.search(text):
        return True
    return bool(words & set(INSTRUMENT_CATEGORIES)) and words <= (
        set(INSTRUMENT_CATEGORIES) | BARE_REQUEST_WORDS
    )


def _rerouted_search(snapshot, intent, message, guided_category, intent_count):
    """Route two observed model mistakes back to the catalog search."""
    text = normalize(message)
    if (
        intent_count == 1
        and isinstance(intent, PolicyQuestion)
        and ACCESSORY_WORDS.search(text)
        and SELL_QUESTION.search(text)
        and not POLICY_TOPIC.search(text)
    ):
        return OutOfScope(
            type="out_of_scope", topic=ACCESSORY_WORDS.search(text).group(0)
        )
    if intent_count == 1 and isinstance(intent, (PolicyQuestion, OutOfScope)):
        outside = OUTSIDE_CATALOG.search(text)
        if (
            outside
            and not ACCESSORY_WORDS.search(text)
            and not POLICY_TOPIC.search(text)
            and (isinstance(intent, OutOfScope) or SELL_QUESTION.search(text))
            and not any(
                outside.group(0) in normalize(p.name)
                for p in snapshot.products.values()
            )
        ):
            # The manual's general text must not imply these are for sale.
            return ProductSearch(type="product_search", query=outside.group(0))
        if (
            PROMOTION_WORDS.search(text)
            and not PROMOTION_RULE.search(text)
            and not POLICY_TOPIC.search(text)
        ):
            return ProductSearch(type="product_search")
        if (
            isinstance(intent, OutOfScope)
            and POLICY_TOPIC.search(text)
            and not ACCESSORY_WORDS.search(text)
        ):
            return PolicyQuestion(type="policy_question")
    if (
        intent_count == 1
        and isinstance(intent, SmallTalk)
        and intent.kind in (None, "greeting")
        and not SOCIAL_WORDS.search(text)
        and not IDENTITY_QUESTION.search(text)
    ):
        return OutOfScope(type="out_of_scope", topic="outro assunto")
    if (
        isinstance(intent, ProductSearch)
        and intent_count == 1
        and ACCESSORY_WORDS.search(text)
    ):
        # The store sells no accessories, whatever search the model proposed.
        return OutOfScope(
            type="out_of_scope", topic=ACCESSORY_WORDS.search(text).group(0)
        )
    if (
        guided_category
        and isinstance(intent, PaymentOptions)
        and intent.product_reference is not None
        and intent.product_reference.kind == "query"
        and intent.payment_method is None
        and not PAYMENT_MENTION.search(text)
    ):
        # "Yamaha", answering "which brand?", is a filter and not yet a quote.
        return ProductSearch(
            type="product_search",
            query=intent.product_reference.query,
            quantity=intent.quantity,
        )
    if isinstance(intent, OutOfScope) and intent_count == 1:
        # "mostre as guitarras" sent out of scope; accessories remain out of scope.
        named = _named_categories(snapshot, message)
        wanted = LIST_WORDS.search(text) or PURCHASE_WORDS.search(text)
        if len(named) == 1 and wanted and not ACCESSORY_WORDS.search(text):
            return ProductSearch(type="product_search", category=named.pop())
        if not ACCESSORY_WORDS.search(text):
            # A store brand sent out of scope, as seen after a failed search.
            brands = (set(_words(message)) & set(_brand_names(snapshot))) - set(
                INSTRUMENT_CATEGORIES
            )
            if len(brands) == 1:
                return ProductSearch(type="product_search", query=brands.pop())
    return intent


def _active_promotions(snapshot, intent, message):
    """Real active promotions matching the instruments and every name typed."""
    named = _named_categories(snapshot, message)
    if intent.category:
        named = {intent.category}
    products = (
        [p for category in named for p in _category_products(snapshot, category)]
        if named
        else list(snapshot.products.values())
    )
    # Short model codes such as "D-8" also count, or another model could answer.
    vocabulary = {
        word
        for product in snapshot.products.values()
        for word in _words(product.name)
        if len(word) >= MIN_RECOVERED_TERM_LENGTH or re.search(r"[0-9]", word)
    }
    typed = (set(_words(message)) & vocabulary) - set(INSTRUMENT_CATEGORIES)
    typed -= {w for w in typed if w.isdigit()}
    written = _words(message)
    brands = set(_brand_names(snapshot))
    for word, following in zip(written, written[1:]):
        if (
            word in brands
            and following not in vocabulary
            and following not in AFTER_NAME_WORDS
        ):
            return []
    ids = []
    for product in sorted(products, key=lambda p: p.product_id):
        promotions = snapshot.promotions_by_product[product.product_id]
        if not any(p.is_active for p in promotions):
            continue
        if typed <= set(_words(product.name)):
            ids.append(product.product_id)
    return ids


def _brand_names(snapshot):
    """Catalog brands by their normalized word, taken from leading name words."""
    brands = {_words(p.name)[0]: p.name.split()[0] for p in snapshot.products.values()}
    for generic in GENERIC_NAME_WORDS:
        brands.pop(generic, None)
    if "music" in brands:
        brands["music"] = "Music Man"  # The only two-word brand in the catalog.
    return brands


def _spelling_correction(snapshot, query):
    """The catalog word closest to a typed name that matches no product."""
    word = normalize(query)
    if len(word) < MIN_CORRECTABLE_LENGTH or " " in word:
        return None
    # Brands only, and strict: ordinary words are close to many product words.
    if word in NOT_MISSPELLED:
        return None
    close = difflib.get_close_matches(word, _brand_names(snapshot), n=1, cutoff=0.85)
    return close[0] if close else None


def _catalog_guide(snapshot, intent):
    products = (
        _category_products(snapshot, intent.category)
        if intent.category
        else list(snapshot.products.values())
    )
    brand_words = _brand_names(snapshot)
    brands = []
    for product in sorted(products, key=lambda p: p.product_id):
        if product.status != "active" or product.stock_quantity == 0:
            continue
        for word in _words(product.name):
            brand = brand_words.get(word)
            if brand and brand not in brands:
                brands.append(brand)
                break
    sellable = [
        p.price_brl for p in products if p.status == "active" and p.stock_quantity > 0
    ]
    names = {snapshot.categories[p.category_id].name for p in products}
    return CatalogGuide(
        category=names.pop() if intent.category and len(names) == 1 else None,
        brands=tuple(brands[:MAX_GUIDE_BRANDS]),
        lowest_price_brl=min(sellable, default=None),
        highest_price_brl=max(sellable, default=None),
    )


LOW_PRICE_PHRASE = re.compile(
    r"\b(mais|precos?|valor|valores|custo|bem|muito|por)\s+(mais\s+)?baixos?\b"
    r"|\bbaixos?\s+(custo|preco|valor)"
)


def _named_categories(snapshot, message):
    """Categories of instruments typed; "preço baixo" does not name a bass."""
    words = set(_words(message))
    if LOW_PRICE_PHRASE.search(normalize(message)):
        words -= {"baixo", "baixos"}
    return {
        INSTRUMENT_CATEGORIES[word]
        for word in words
        if word in INSTRUMENT_CATEGORIES
        and _category_products(snapshot, INSTRUMENT_CATEGORIES[word])
    }


def _words(text):
    return re.findall(r"[^\W_]+(?:-[^\W_]+)*", normalize(text))


def _category_products(snapshot, category):
    wanted = normalize(category)
    ids = {
        c.category_id
        for c in snapshot.categories.values()
        if wanted in normalize(c.name)
    }
    return [p for p in snapshot.products.values() if p.category_id in ids]


def _checked_search_terms(snapshot, intent, message):
    """Keep search terms grounded in the customer's words, compared as whole words.

    The model may invent "viola" for "violao" or lose a typed brand. Python only
    corrects cases the current message settles, and never guesses between options.
    """
    typed = _words(message)
    query, category = intent.query, intent.category
    if category and normalize(category) in INSTRUMENT_CATEGORIES:
        # The contract's category is free text: "Violão" is not part of "Violões".
        alias = INSTRUMENT_CATEGORIES[normalize(category)]
        if _category_products(snapshot, alias):
            category = alias
    named = _named_categories(snapshot, message)
    inferred = next(iter(named)) if len(named) == 1 else None
    if query and _typed_amounts(query) == {intent.max_price_brl}:
        # The budget copied into the name would match models such as "FG800".
        query = None
    if query and normalize(query) in INSTRUMENT_CATEGORIES:
        alias = INSTRUMENT_CATEGORIES[normalize(query)]
        if _category_products(snapshot, alias):
            query, category = None, category or alias
    corrected = False
    if query and not any(
        normalize(query) in normalize(p.name) for p in snapshot.products.values()
    ):
        correction = _spelling_correction(snapshot, query)
        if correction and normalize(query) in typed:
            query, corrected = correction, True
    if (
        query
        and inferred
        and not any(
            normalize(query) in normalize(p.name)
            for p in _category_products(snapshot, category or inferred)
        )
    ):
        # A price, adjective, or invented word cannot hide the instrument typed.
        query, category = None, category or inferred
    if query and not corrected and not set(_words(query)) <= set(typed):
        category = category or inferred
        if category:
            query = None
    if not query:
        category = category or inferred
    if not query and category:
        vocabulary = {
            word
            for product in _category_products(snapshot, category)
            for word in _words(product.name)
            if len(word) >= MIN_RECOVERED_TERM_LENGTH
        }
        found = (set(typed) & vocabulary) - set(INSTRUMENT_CATEGORIES)
        if len(found) == 1:
            query = found.pop()
    if (query, category) == (intent.query, intent.category):
        return intent
    return intent.model_copy(update={"query": query, "category": category})


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
# Payment proposals need evidence in the current message. Python never chooses a
# method from a keyword; it only rejects unsupported model proposals. PIX remains
# stricter because it changes prices. Ambiguous negations ask for clarification.
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
    # "Bass 3X" is a model name, not an installment count.
    text = re.sub(r"\bbass [0-9]+ ?x\b", "", normalize(message))
    return re.search(r"\bpix\b", text) is not None and not _NOT_PIX.search(text)


PAYMENT_EVIDENCE = {
    "credit": re.compile(r"\b(?:credito|credit|cartao|parcel\w*|vezes|[0-9]+ ?x)\b"),
    "debit": re.compile(r"\b(?:debito|debit|cartao)\b"),
    "boleto": re.compile(r"\bboleto\b"),
    "combined": re.compile(r"\b(?:combin\w*|meio a meio|dividi\w*)\b"),
}
NEGATED_PAYMENT = re.compile(r"\b(?:nao|nem|vez de|sem(?!\s+juros\b))\b")


def payment_declared(method, message):
    if method == "pix":
        return pix_declared(message)
    text = normalize(message)
    return (
        method in PAYMENT_EVIDENCE
        and PAYMENT_EVIDENCE[method].search(text) is not None
        and not NEGATED_PAYMENT.search(text)
    )


def payment_follow_up(message):
    """Recognize a payment-only follow-up, never a new product or quantity."""
    original = normalize(message)
    text = re.sub(rf"\b{_COUNT}\s*(?:x|vezes|parcelas?)\b", " ", original)
    return (
        PAYMENT_MENTION.search(original) is not None
        and re.fullmatch(
            r"[\s?!.]*(?:(?:e|em|no|na|de|a|com|pelo|pela|via|quanto|fica|ficaria|"
            r"seria|quero|pagar|pago|por|favor|pix|credito|credit|debito|debit|cartao|boleto|vista|prazo|sem|"
            r"juros|parcelado)\b[\s?!.]*)+",
            text,
        )
        is not None
    )


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
        self._guided_category = None
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
        except ProviderConnectionError as error:
            LOGGER.warning("Extraction failed: %s", type(error).__name__)
            return self._finish(message, MODEL_UNAVAILABLE)
        except (ProposalError, ProviderError) as error:
            LOGGER.warning("Extraction failed: %s", type(error).__name__)
            if (
                self.session.pending
                or not POLICY_TOPIC.search(normalize(message))
                or not hasattr(self.provider, "explain")
            ):
                return self._finish(
                    message, "Não consegui interpretar sua mensagem. Tente novamente."
                )
            # The manual route is a separate call and can still answer this.
            proposal = IntentTurn(intents=[PolicyQuestion(type="policy_question")])

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
        guided_category, self._guided_category = self._guided_category, None
        notes = []
        checked = []
        for intent in intents:
            intent = _rerouted_search(
                self.snapshot, intent, message, guided_category, len(intents)
            )
            if isinstance(intent, ProductSearch):
                if (
                    intent.max_price_brl is not None
                    and intent.max_price_brl not in typed_amounts
                ):
                    intent = intent.model_copy(update={"max_price_brl": None})
                    if BUDGET_HINT.search(normalize(message)):
                        notes.append(BUDGET_IGNORED)
                if (
                    not intent.category
                    and guided_category
                    and not _named_categories(self.snapshot, message)
                ):
                    # Answering "which brand?" continues the instrument just asked.
                    intent = intent.model_copy(update={"category": guided_category})
                original_query = intent.query
                intent = _checked_search_terms(self.snapshot, intent, message)
                if (
                    original_query
                    and not intent.query
                    and set(_words(original_query)) <= set(_words(message))
                    and not _typed_amounts(original_query)
                    and normalize(original_query) not in INSTRUMENT_CATEGORIES
                ):
                    notes.append(SEARCH_FILTER_DROPPED)
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
            unavailable = self._unavailable_product(outcome, resolved)
            if unavailable is not None:
                alternatives = self._alternatives(unavailable)
                if alternatives:
                    notes.append(render_alternatives(alternatives))
            if (
                isinstance(intent, PaymentOptions)
                and outcome.status == "needs_information"
                and resolved is not None
                and choices is None
                and intent.product_reference is not None
                and intent.payment_method is None
                and intent.installments is None
                and not prior
                and not PAYMENT_MENTION.search(normalize(self._message))
            ):
                # A chosen model: show its facts while asking for what is missing.
                # The card is not a new list, so earlier positions stay valid.
                card = quote_product(
                    self.snapshot,
                    resolved,
                    ProductSearch(type="product_search", quantity=intent.quantity),
                )
                if card.status == "success":
                    results.append(card)
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
        if (
            self._intent_count == 1
            and isinstance(intent, (OutOfScope, SmallTalk, PolicyQuestion))
            and IDENTITY_QUESTION.search(normalize(self._message))
        ):
            data = SmallTalkData(template="identity")
            return SmallTalkResult(status="success", data=data), None, None
        if (
            self._intent_count == 1
            and isinstance(intent, ProductSearch)
            and PROMOTION_WORDS.search(normalize(self._message))
        ):
            result = self._promotions(intent)
            return result, result if result.status == "success" else None, None
        if isinstance(intent, ProductSearch):
            result = search_catalog(self.snapshot, intent)
            if (
                result.status == "success"
                and result.data.total_matches >= MIN_GUIDED_MATCHES
                and _is_broad_request(intent, self._message)
            ):
                self._guided_category = intent.category
                data = result.data.model_copy(
                    update={
                        "products": (),
                        "guide": _catalog_guide(self.snapshot, intent),
                    }
                )
                result = result.model_copy(update={"data": data})
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
        """Drop payment methods not supported by this message, without inferring one."""
        if (
            not isinstance(intent, (ProductSearch, *QUOTES))
            or intent.payment_method is None
            or (supplied is not None and "payment_method" not in supplied)
            or payment_declared(intent.payment_method, self._message)
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
        if declared.quantity is not None and (
            intent.quantity is None or payment_follow_up(self._message)
        ):
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

    def _unavailable_product(self, outcome, resolved):
        if outcome.status == "unavailable" and resolved is not None:
            return resolved
        if (
            isinstance(outcome, ProductSearchResult)
            and outcome.status == "success"
            and outcome.data.total_matches == 1
            and outcome.data.products
        ):
            product = self.snapshot.products[outcome.data.products[0].product_id]
            if product.status != "active" or product.stock_quantity == 0:
                return product.product_id
        return None

    def _alternatives(self, product_id):
        """Same-category products on sale, closest in list price (manual §7.3)."""
        chosen = self.snapshot.products[product_id]
        options = sorted(
            (
                p
                for p in self.snapshot.products.values()
                if p.category_id == chosen.category_id
                and p.product_id != product_id
                and p.status == "active"
                and p.stock_quantity > 0
            ),
            key=lambda p: (abs(p.price_brl - chosen.price_brl), p.product_id),
        )[:MAX_ALTERNATIVES]
        quotes = []
        for option in options:
            found = quote_product(
                self.snapshot, option.product_id, ProductSearch(type="product_search")
            )
            if found.status == "success":
                quotes.extend(found.data.products)
        return quotes

    def _promotions(self, intent):
        ids = _active_promotions(self.snapshot, intent, self._message)
        if not ids:
            return ProductSearchResult(
                status="not_found",
                reason_code="NO_ACTIVE_PROMOTION",
                policy_references=("6",),
            )
        quotes = []
        for product_id in ids:
            found = quote_product(
                self.snapshot,
                product_id,
                # Already validated on the intent; its budget is a Decimal now.
                ProductSearch(type="product_search").model_copy(
                    update={
                        "quantity": intent.quantity,
                        "max_price_brl": intent.max_price_brl,
                    }
                ),
            )
            if found.status == "not_found":
                continue  # Above the requested budget.
            if found.status != "success":
                return found
            quotes.extend(found.data.products)
        if not quotes:
            return ProductSearchResult(
                status="not_found",
                reason_code="NO_ACTIVE_PROMOTION",
                policy_references=("6",),
            )
        return ProductSearchResult(
            status="success",
            data=CatalogData(products=tuple(quotes), total_matches=len(quotes)),
            policy_references=("6",),
        )

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
            data = explain_policy(
                self.provider,
                question,
                on_policy_topic=bool(POLICY_TOPIC.search(normalize(question))),
            )
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
                # "ukulele Kala KA-C": the product type is not part of the name.
                named = [
                    word
                    for word in reference.query.split()
                    if normalize(word) not in INSTRUMENT_CATEGORIES
                ]
                if found.status == "not_found" and named:
                    found = search_catalog(
                        self.snapshot,
                        ProductSearch(type="product_search", query=" ".join(named)),
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
        if resolved is not None:
            product = self.snapshot.products[resolved]
            if product.status != "active" or product.stock_quantity == 0:
                # No totals or further questions for something not for sale.
                return (
                    _result("payment_options", "unavailable", "PRODUCT_NOT_FOR_SALE"),
                    None,
                    resolved,
                )
            text = normalize(self._message)
            if (
                INSTALLMENT_COUNT_QUESTION.search(text)
                and intent.payment_method in (None, "credit")
                and not OTHER_METHOD.search(text)
            ):
                # Asking the limit is not a purchase: answer for one unit on credit.
                intent = intent.model_copy(
                    update={
                        "quantity": intent.quantity or 1,
                        "payment_method": "credit",
                    }
                )
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
                    reason_code=(
                        "PRODUCT_NOT_SHIPPABLE"
                        if quote.reason_code == "PRODUCT_NOT_FOR_SALE"
                        else quote.reason_code
                    ),
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
