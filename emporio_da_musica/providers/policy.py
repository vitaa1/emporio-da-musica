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

MAX_POLICY_ANSWER = 1000
DEFAULT_MANUAL = Path(__file__).with_name("store_manual.txt")

# The supplied manual has conflicting phones/emails (ARCHITECTURE.md, P03), so no
# contact may be published from model prose, including obfuscated forms.
CONTACT_WORDS = re.compile(
    r"@|\barroba\b|\bponto\s*com\b|www|https?:|wa\.me|\.com\b|emporiodamusica",
    re.IGNORECASE,
)
POSTAL_CODE = re.compile(r"\b\d{5}-\d{3}\b")
DIGIT_SEPARATORS = re.compile(r"(?<=\d)[\s().\-/]+(?=\d)")
# Claims that an action was executed; no such capability exists.
ACTION_CLAIMS = re.compile(
    r"\b(registrei|encaminhei|aprovei|reembolsei|cancelei|transferi|"
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


def explain_policy(provider: PolicyProvider, question: str) -> PolicyData:
    raw = provider.explain(PolicyRequest(question=question))
    try:
        answer = PolicyAnswer.model_validate_json(raw)
    except ValidationError:
        raise PolicyAnswerError("Invalid policy answer") from None
    if not answer.covered:
        raise NotCovered("Question not covered by the manual")
    text = unicodedata.normalize("NFKC", answer.answer)
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
    return data
