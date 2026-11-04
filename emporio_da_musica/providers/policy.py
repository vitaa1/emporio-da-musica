"""Validate model-written general policy explanations before display.

These checks are Python guards on model prose. They reduce, but cannot eliminate,
prompt-injection risk: semantic grounding is evaluated separately.
"""

import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from ..contracts.common import PolicyReference
from ..contracts.results import PolicyData
from .base import PolicyProvider, PolicyRequest

# General warranty explanations use reviewed text: a schema-valid model response
# mixed the warranty rule with LGPD. The model selects sections, not these facts.
WARRANTY_SECTIONS = {"8", "8.1", "8.2", "8.3"}
WARRANTY_ANSWER = PolicyData(
    answer=(
        "Segundo o manual da loja, a garantia legal é de 90 dias contra defeitos "
        "de fabricação, contados do recebimento. A maioria dos fabricantes oferece "
        "garantia própria, que pode variar de 6 meses a 2 anos; o prazo e as "
        "condições de cada produto estão no certificado do instrumento. "
        "O manual exclui desgaste natural, mau uso, quedas, condições climáticas "
        "extremas, modificações ou reparos não autorizados e danos estéticos que "
        "não afetem o funcionamento. Isso não confirma cobertura de um caso individual."
    ),
    policy_references=("8.1", "8.2", "8.3"),
)

# A model answer about deadlines gave one of three different periods as the rule.
RETURN_SECTIONS = {"4", "4.1", "4.2", "4.3", "4.4"}
DEADLINE_QUESTION = re.compile(r"\b(prazo|prazos|quanto tempo|quantos dias)\b")
RETURN_DEADLINES_ANSWER = PolicyData(
    answer=(
        "Segundo o manual da loja, o prazo depende do motivo. Arrependimento em "
        "compra online: até 7 dias corridos após o recebimento. Defeito de "
        "fabricação: troca em até 30 dias corridos após a compra; depois disso, "
        "pela garantia do fabricante. Preferência (cor, modelo ou tamanho): até "
        "7 dias, mediante disponibilidade, e o manual não define a partir de quando "
        "esse prazo conta. No arrependimento, o reembolso sai em até 10 dias úteis. "
        "Isso não confirma um caso individual."
    ),
    policy_references=("4.1", "4.2", "4.3"),
)

# Reviewed text for a question the model answered but marked as uncovered.
STACKING_SECTIONS = {"3", "3.1", "6", "6.1", "6.2", "6.3"}
STACKING_QUESTION = re.compile(r"\b(acumul\w*|cumulativ\w*)\b")
STACKING_ANSWER = PolicyData(
    answer=(
        "Segundo o manual da loja, os descontos não são cumulativos: o desconto de "
        "5% no PIX não se aplica a produtos que já estão em promoção."
    ),
    policy_references=("6",),
)

HOURS_QUESTION = re.compile(
    # Words about this store: "que horário abre o aeroporto?" must not match.
    r"\b(voces?|vcs|loja|abrem|fecham|funcionam|atendem)\b"
)
HOURS_ANSWER = PolicyData(
    answer=(
        "A loja funciona de segunda a sexta, das 9h às 18h, e aos sábados, das 9h "
        "às 13h. Domingos e feriados a loja fica fechada. Em datas especiais, o "
        "horário pode ser estendido."
    ),
    policy_references=("2",),
)

# Whether a campaign is running comes from promotion records, never model prose (§7.3).
CAMPAIGN_NAMES = (
    r"black friday|aniversario da loja|volta as aulas|queima de estoque|"
    r"semana do musico|liquidacao de inverno|pascoa|oferta especial|desconto exclusivo"
)
CAMPAIGN_STATUS_CLAIM = re.compile(
    rf"\b({CAMPAIGN_NAMES})\b.*\b(ativ[oa]s?|vigente|valendo|vale|em andamento|"
    rf"disponive(l|is))\b|\b(ativ[oa]s?|vigente|valendo|em andamento)\b.*\b({CAMPAIGN_NAMES})\b"
)
# The manual's calendar (§6.1) gives each campaign's month and range; other percentages
# next to a campaign name are status claims.
CAMPAIGN_PERCENT = re.compile(rf"\b({CAMPAIGN_NAMES})\b.*[0-9]+ ?%")
CAMPAIGN_MONTH = re.compile(r"\b(novembro|agosto|fevereiro)\b")

# Clear general questions answered from reviewed manual text, without the model.
# Observed live: a small model sends these to product, order, or scope routes.
_REVIEWED_QUESTIONS = (
    (
        r"\baceita\w*\b.*\b(boleto|debito|pix|cartao|credito)\b",
        "Aceitamos PIX (5% de desconto sobre o preço de tabela, sem somar com "
        "promoção), cartão de débito, cartão de crédito em até 12x sem juros e boleto "
        "(compensação em até 3 dias úteis).",
        ("3",),
    ),
    (
        r"^(em |ate )?quantas (vezes|parcelas)( (posso|da|consigo|pode)( pra| para)?"
        r"( parcelar| dividir)?)?$|\bcomo funciona o parcelamento\b",
        "Dá para parcelar em até 12x sem juros, conforme o valor: de 4x a 6x a parcela "
        "mínima é de R$ 80,00 e de 7x a 12x é de R$ 100,00. Em 2x ou 3x, parcela a "
        "partir de R$ 100,00 está ok; abaixo disso, precisa de confirmação da loja. "
        "Me diga o instrumento e eu calculo.",
        ("3.1",),
    ),
    (
        r"\b(como|quando|prazo)\b.*\breembolso\b",
        "No arrependimento de compra online, o reembolso é feito na mesma forma de "
        "pagamento original, em até 10 dias úteis.",
        ("4.1",),
    ),
    (
        r"\bfrete\b.*\bdevolucao\b",
        "No arrependimento de compra online, o frete de devolução é por conta da loja. "
        "O manual não define esse custo para outros casos.",
        ("4.1",),
    ),
    (
        r"\bboquilhas?\b",
        "Boquilhas de instrumentos de sopro não são elegíveis para troca, por questões "
        "de higiene.",
        ("4.4",),
    ),
    (
        r"\bcomo funciona o frete\b|\bfrete\b.*\b(outras? cidades?|outros? estados?)\b",
        "Na região metropolitana de Campo Grande, o frete é grátis acima de R$ 500,00 "
        "e custa R$ 35,00 abaixo disso, com entrega em 1 a 3 dias úteis. Para outras "
        "cidades, enviamos por PAC, SEDEX ou Jadlog, com valor calculado pelo CEP, pelo "
        "peso e pelas dimensões do produto.",
        ("5.1", "5.2"),
    ),
    (
        r"\b(sedex|pac|jadlog)\b",
        "Para fora da região metropolitana de Campo Grande, os prazos estimados são: "
        "PAC, 5 a 12 dias úteis; SEDEX, 2 a 5; Jadlog, 3 a 8. Todos têm rastreamento e "
        "seguro incluído. O valor depende do CEP, do peso e das dimensões do produto.",
        ("5.2",),
    ),
    (
        r"\b(chegou|veio|recebi|entrega\w*)\b.*\b(avariad\w*|danificad\w*|amassad\w*)\b"
        r"|\bavaria\b",
        "Em caso de avaria no transporte, recuse o recebimento e entre em contato "
        "imediatamente com a loja. Todos os envios têm seguro contra extravios e danos.",
        ("5.2",),
    ),
    (
        r"\b(segur\w*|reserv\w*|mantem|manter|garant\w*)\b.*\bprecos?\b|\brain check\b",
        "Não: promoções dependem do estoque, e produto esgotado durante a promoção não "
        "dá direito a reserva de preço.",
        ("6.2",),
    ),
    (
        r"\bquando\b.*\b(black friday|aniversario da loja|volta as aulas"
        r"|semana do musico)\b",
        "As campanhas costumam ser: Volta às Aulas em fevereiro, Aniversário da Loja "
        "em agosto, Black Friday em novembro e Semana do Músico na semana de 22 de "
        "novembro. Isso não indica promoção ativa agora; posso listar as que estão "
        "valendo.",
        ("6.1",),
    ),
    (
        r"\b(excluir|exclusao|apagar|deletar|remover)\b.*\bdados\b",
        "Você pode pedir a exclusão dos seus dados a qualquer momento pelo WhatsApp ou "
        "e-mail da loja. Eu não consigo fazer isso por aqui, então nada foi excluído.",
        ("9",),
    ),
)
REVIEWED_QUESTIONS = tuple(
    (re.compile(pattern), PolicyData(answer=answer, policy_references=references))
    for pattern, answer, references in _REVIEWED_QUESTIONS
)

MAX_POLICY_ANSWER = 1000
DEFAULT_MANUAL = Path(__file__).with_name("store_manual.txt")

# The supplied manual has conflicting phones/emails (ARCHITECTURE.md, P03), so no
# contact may be published from model prose, including obfuscated forms.
CONTACT_WORDS = re.compile(
    r"@|\barroba\b|\bponto\s*com\b|www|https?:|wa\.me|\.com\b|emporiodamusica|"
    r"\binstagram\b|\bgmail\b",
    re.IGNORECASE,
)
POSTAL_CODE = re.compile(r"\b\d{5}-\d{3}\b")
DIGIT_SEPARATORS = re.compile(r"(?<=\d)[\s().\-/]+(?=\d)")
# Claims that an action was executed; no such capability exists.
ACTION_CLAIMS = re.compile(
    r"\b(registrei|encaminhei|aprovei|reembolsei|cancelei|transferi|solicitei|abri|"
    r"efetuei|agendei|estornei|processei|estornad[oa]s?|"
    r"(registrad|encaminhad|aprovad|reembolsad|cancelad|transferid)[oa]s?)\b",
    re.IGNORECASE,
)


class PolicyAnswer(BaseModel):
    """Provider schema; answer and sections are required only when covered."""

    model_config = ConfigDict(extra="forbid", strict=True)

    covered: bool
    answer: str = ""
    policy_references: tuple[PolicyReference, ...] = ()


class NotCovered(ValueError):
    """The manual does not answer the question; show the scope template."""


class PolicyAnswerError(ValueError):
    """The provider answer is malformed or unsupported; no prose is shown."""


class ContactConflict(ValueError):
    """The answer depends on contacts that the manual states inconsistently."""


def reviewed_question_answer(message: str) -> PolicyData | None:
    """A reviewed answer for one clear general question; never for a specific quote."""
    folded = "".join(
        c
        for c in unicodedata.normalize("NFD", message.casefold())
        if not unicodedata.combining(c)
    )
    text = " ".join(folded.split()).strip(" ?!.")
    if "?" in text or re.search(r"[0-9]", text):
        return None  # Several questions, or a product, quantity, or order number.
    for pattern, answer in REVIEWED_QUESTIONS:
        if pattern.search(text):
            return answer
    return None


def _numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"[0-9]+", text)}


def _reviewed_answer(question, references):
    """Reviewed text selected by Python from the question and the model's sections."""
    folded = "".join(
        c
        for c in unicodedata.normalize("NFD", question.casefold())
        if not unicodedata.combining(c)
    )
    sections = set(references)
    if not sections:
        return None
    if sections <= WARRANTY_SECTIONS:
        return WARRANTY_ANSWER
    if sections <= {"2"} and HOURS_QUESTION.search(folded):
        return HOURS_ANSWER
    if sections <= RETURN_SECTIONS and DEADLINE_QUESTION.search(folded):
        return RETURN_DEADLINES_ANSWER
    if sections <= STACKING_SECTIONS and STACKING_QUESTION.search(folded):
        return STACKING_ANSWER
    return None


def explain_policy(
    provider: PolicyProvider, question: str, *, on_policy_topic: bool = False
) -> PolicyData:
    """Validate an answer; text marked as uncovered is never displayed."""
    raw = provider.explain(PolicyRequest(question=question))
    try:
        answer = PolicyAnswer.model_validate_json(raw)
    except ValidationError:
        raise PolicyAnswerError("Invalid policy answer") from None
    if not answer.covered:
        reviewed = _reviewed_answer(question, answer.policy_references)
        if on_policy_topic and reviewed:
            return reviewed
        raise NotCovered("Question not covered by the manual")
    text = "".join(
        c
        for c in unicodedata.normalize("NFKC", answer.answer)
        if unicodedata.category(c) != "Cf"
    )
    if any(c.isdigit() and not c.isascii() for c in text):
        raise ContactConflict("Non-ASCII digits are not displayed")
    if not text.strip() or len(text) > MAX_POLICY_ANSWER:
        raise PolicyAnswerError("Empty or oversized policy answer")
    try:
        data = PolicyData(answer=text, policy_references=answer.policy_references)
    except ValidationError:
        raise PolicyAnswerError("Invalid policy answer") from None
    folded = "".join(
        c
        for c in unicodedata.normalize("NFD", text.casefold())
        if not unicodedata.combining(c)
    )
    joined = DIGIT_SEPARATORS.sub("", POSTAL_CODE.sub(" ", folded))
    if CONTACT_WORDS.search(folded):
        raise ContactConflict("Contact details require confirmation")
    if re.search(r"[0-9]{8,}", joined):
        raise ContactConflict("Contact details require confirmation")
    if CAMPAIGN_STATUS_CLAIM.search(folded) or (
        CAMPAIGN_PERCENT.search(folded) and not CAMPAIGN_MONTH.search(folded)
    ):
        raise PolicyAnswerError("Policy answer asserts a campaign status")
    if ACTION_CLAIMS.search(folded):
        raise PolicyAnswerError("Policy answer claims an executed action")
    manual = getattr(provider, "manual", None) or DEFAULT_MANUAL.read_text("utf-8")
    if not _numbers(text) <= _numbers(manual):
        # Every number must exist in the manual: no invented prices or discounts.
        raise PolicyAnswerError("Policy answer contains unsupported numbers")
    if set(data.policy_references) <= WARRANTY_SECTIONS:
        return WARRANTY_ANSWER
    return _reviewed_answer(question, data.policy_references) or data
