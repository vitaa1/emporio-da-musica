"""Gaps found by probing the challenge requirements with new wording."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderRequest,
)
from emporio_da_musica.providers.ollama import OllamaProvider

from .support import FakeProvider, turn

DEMO = Path(__file__).parent.parent / "data" / "demo"
HOURS = {"covered": True, "answer": "Domingos fechado.", "policy_references": ["2"]}


@pytest.fixture
def demo():
    return Controller(
        load_snapshot(DEMO),
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def policy(question=None):
    return {"type": "policy_question", "topic": None, "question": question}


class ServerError:
    def open(self, *args, **kwargs):
        raise HTTPError("u", 500, "x", {}, BytesIO(b"token repeat limit"))


def test_http_error_is_not_a_connection_failure():
    provider = OllamaProvider()
    provider.opener = ServerError()
    with pytest.raises(ProviderError) as error:
        provider.propose(ProviderRequest(message="x"))
    assert not isinstance(error.value, ProviderConnectionError)


def test_failed_extraction_of_a_policy_message_uses_the_manual(demo):
    demo.provider.responses.append(ProviderError("repeat limit"))
    demo.provider.policy_responses.append(HOURS)
    response = demo.handle("vocês abrem domingo?")
    assert (
        "Domingos e feriados" in response.text and "indisponível" not in response.text
    )


def test_failed_extraction_of_other_messages_stays_honest(demo):
    demo.provider.responses.append(ProviderError("repeat limit"))
    response = demo.handle("quero o de sempre")
    assert "interpretar" in response.text and not demo.provider.policy_requests


def test_unreachable_server_does_not_call_the_policy_route(demo):
    demo.provider.responses.append(ProviderConnectionError("x"))
    response = demo.handle("vocês abrem domingo?")
    assert "indisponível" in response.text and not demo.provider.policy_requests


@pytest.mark.parametrize("message", ["vocês vendem violino?", "tem saxofone?"])
def test_policy_route_cannot_claim_an_instrument_outside_the_catalog(demo, message):
    response = turn(demo, policy(), message=message)
    assert response.results[0].operation == "product_search"
    assert response.results[0].status == "not_found"
    assert not demo.provider.policy_requests


def test_uncovered_answer_on_a_policy_topic_is_not_displayed(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "Em até 7 dias.", "policy_references": ["2"]}
    )
    response = turn(demo, policy(), message="qual a política de horário e prazo?")
    assert "Em até 7 dias" not in response.text and "foge" in response.text


def test_contradictory_answer_still_passes_number_validation(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "Em até 77777 dias.", "policy_references": ["2"]}
    )
    response = turn(demo, policy(), message="qual o prazo?")
    assert "77777" not in response.text


def test_uncovered_answer_off_policy_topic_stays_out_of_scope(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "Paris.", "policy_references": ["2"]}
    )
    response = turn(demo, policy(), message="qual a capital da frança?")
    assert "Paris" not in response.text and "foge" in response.text


def test_return_deadline_question_uses_the_reviewed_summary(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "7 dias.", "policy_references": ["4.1"]}
    )
    text = turn(demo, policy(), message="qual o prazo para devolução?").text
    assert "7 dias corridos após o recebimento" in text
    assert "30 dias corridos após a compra" in text
    assert "não define" in text


@pytest.mark.parametrize("intent", [policy(), {"type": "out_of_scope", "topic": "x"}])
def test_promotion_search_lists_real_active_promotions(demo, intent):
    response = turn(demo, intent, message="tem ukulele em promoção?")
    products = response.results[0].data.products
    assert {q.name.split()[0] for q in products} == {"Kalani", "Ohana"}
    assert all(q.promotion_percent for q in products)


def test_named_product_without_promotion_says_so(demo):
    intent = {"type": "out_of_scope", "topic": "promoção"}
    response = turn(demo, intent, message="o Fender Stratocaster está em promoção?")
    assert response.results[0].data.notice
    assert "promoção ativa" in response.text
    assert "R$" in response.text  # §7.3: the current price is presented.


def test_promotion_rule_question_stays_on_the_policy_route(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "Não acumula.", "policy_references": ["6"]}
    )
    response = turn(demo, policy(), message="a promoção acumula com pix?")
    assert "não são cumulativos" in response.text


def test_payment_quote_in_promotion_is_not_rerouted(demo):
    intent = {
        "type": "payment_options",
        "product_reference": {"kind": "query", "query": "Crafter HT-100"},
        "quantity": 1,
        "payment_method": "pix",
    }
    response = turn(demo, intent, message="um Crafter HT-100 em promoção no pix")
    assert response.results[-1].data.final_total_brl == 1967.18 or (
        str(response.results[-1].data.final_total_brl) == "1967.18"
    )


@pytest.mark.parametrize(
    "message", ["me conta uma piada", "faz meu dever de matemática"]
)
def test_unrelated_request_labeled_as_greeting_is_out_of_scope(demo, message):
    intent = {"type": "small_talk", "kind": "greeting"}
    assert turn(demo, intent, message=message).results[0].operation == "out_of_scope"


@pytest.mark.parametrize("message", ["oi, tudo bem?", "bom dia", "olá"])
def test_real_greetings_stay_greetings(demo, message):
    intent = {"type": "small_talk", "kind": "greeting"}
    assert turn(demo, intent, message=message).results[0].operation == "small_talk"


@pytest.mark.parametrize(
    "intent",
    [
        {"type": "out_of_scope", "topic": "x"},
        {"type": "small_talk", "kind": "greeting"},
    ],
)
def test_identity_question_has_a_persona_answer(demo, intent):
    text = turn(demo, intent, message="quem é você?").text
    assert "assistente virtual do Empório da Música" in text


def test_policy_topic_sent_out_of_scope_uses_the_manual(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "Depende do manual.", "policy_references": ["5"]}
    )
    intent = {"type": "out_of_scope", "topic": "frete"}
    assert "Depende do manual" in turn(demo, intent, message="como é o frete?").text


def test_accessory_delivery_question_stays_out_of_scope(demo):
    intent = {"type": "out_of_scope", "topic": "palheta"}
    response = turn(demo, intent, message="qual o frete da palheta?")
    assert response.results[0].operation == "out_of_scope"
