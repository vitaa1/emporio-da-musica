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
        "de fabricação, contados do recebimento. A garantia adicional do fabricante "
        "varia; consulte o prazo e as condições no certificado do instrumento. "
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
    if ACTION_CLAIMS.search(folded):
        raise PolicyAnswerError("Policy answer claims an executed action")
    manual = getattr(provider, "manual", None) or DEFAULT_MANUAL.read_text("utf-8")
    if not _numbers(text) <= _numbers(manual):
        # Every number must exist in the manual: no invented prices or discounts.
        raise PolicyAnswerError("Policy answer contains unsupported numbers")
    if set(data.policy_references) <= WARRANTY_SECTIONS:
        return WARRANTY_ANSWER
    return _reviewed_answer(question, data.policy_references) or data
