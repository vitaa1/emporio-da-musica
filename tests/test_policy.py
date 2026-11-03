"""General policy answers, scope redirection, small talk, and complaints."""

import json

import pytest

from emporio_da_musica.providers.base import ProviderError
from emporio_da_musica.providers.demo import DemoProvider
from emporio_da_musica.providers.ollama import OllamaProvider

from .support import search, turn


def policy(question=None):
    return {"type": "policy_question", "topic": None, "question": question}


HOURS = {
    "covered": True,
    "answer": "Funcionamos de segunda a sexta, das 9h às 18h.",
    "policy_references": ["2"],
}


def test_policy_answer_is_rendered_with_sections_and_footer(app):
    app.provider.policy_responses.append(HOURS)
    response = turn(app, policy("Qual o horário?"))
    result = response.results[0]
    assert result.status == "success"
    assert result.policy_references == ("2",)
    assert "das 9h às 18h. (Manual da loja, seção 2.)" in response.text
    assert "casos específicos dependem" in response.text


def test_policy_request_carries_only_the_question(app):
    app.provider.policy_responses.append(HOURS)
    turn(app, search("Piano"))
    app.provider.policy_responses.append(HOURS)
    turn(app, policy())
    request = app.provider.policy_requests[-1]
    assert request.question == "synthetic customer message"
    assert set(type(request).model_fields) == {"question"}


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        {"answer": "x", "policy_references": ["2"]},
        {"covered": True, "answer": "x", "policy_references": []},
        {"covered": True, "answer": "x" * 1001, "policy_references": ["2"]},
        {
            "covered": True,
            "answer": "Seu reembolso foi aprovado.",
            "policy_references": ["4.1"],
        },
        {
            "covered": True,
            "answer": "Registrei sua troca.",
            "policy_references": ["4.2"],
        },
        {
            "covered": True,
            "answer": "Hoje há 37% de desconto.",
            "policy_references": ["6"],
        },
        {
            "covered": True,
            "answer": "O frete custa R$ 12,49.",
            "policy_references": ["5"],
        },
        {"covered": True, "answer": "x", "policy_references": ["99"]},
        {"covered": True, "answer": "x", "policy_references": ["2"], "approved": True},
        {"covered": True, "answer": "   ", "policy_references": ["2"]},
        ProviderError("sensitive"),
    ],
)
def test_invalid_or_failed_policy_answers_show_no_prose(app, bad, caplog):
    app.provider.policy_responses.append(bad)
    response = turn(app, policy("Posso trocar?"), search("Piano"))
    assert [r.status for r in response.results] == ["error", "success"]
    assert "Não consegui responder sobre essa política agora" in response.text
    assert "sensitive" not in response.text + caplog.text
    assert "approved" not in response.text


@pytest.mark.parametrize(
    "answer",
    [
        "Ligue para (67) 3341-4444.",
        "Fale pelo 67 3321-4500.",
        "Escreva para contato@empóriodamusica.com.br.",
        "Acesse emporiodamusica.com.br.",
        "Ligue (67) 3333 4444.",
        "Ligue 6 7 3 3 3 3 4 4 4 4.",
        "Escreva para contato arroba loja ponto com.",
        "Acesse www.loja.com.br.",
        "Fale em wa.me/5567999999999.",
    ],
)
def test_conflicting_contacts_are_never_published(app, answer):
    app.provider.policy_responses.append(
        {"covered": True, "answer": answer, "policy_references": ["1.2"]}
    )
    response = turn(app, policy("Qual o telefone?"))
    assert response.results[0].status == "requires_confirmation"
    assert "divergentes" in response.text
    assert "3341" not in response.text and "4444" not in response.text


def test_address_and_postal_code_are_not_treated_as_contacts(app):
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "Estamos na Rua 14 de Maio, 3200 — Centro, CEP 79202-333.",
            "policy_references": ["1.2"],
        }
    )
    response = turn(app, policy("Qual o endereço?"))
    assert response.results[0].status == "success"
    assert "79202-333" in response.text


def test_provider_without_policy_support_reports_unavailable(app):
    app.provider = DemoProvider()
    response = app.handle("/buscar Piano")
    assert response.results[0].status == "success"

    class ExtractOnly:
        def propose(self, request):
            return json.dumps({"intents": [policy()]})

    app.provider = ExtractOnly()
    response = app.handle("Qual o horário?")
    assert response.results[0].status == "unavailable"
    assert "modo de demonstração" in response.text


def test_out_of_scope_redirects_without_partner_stores(app):
    response = turn(app, {"type": "out_of_scope", "topic": "cordas"})
    assert response.results[0].status == "success"
    assert "exclusivamente com instrumentos" in response.text
    assert "não indico outras lojas" in response.text


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("greeting", "Olá!"),
        ("thanks", "prazer"),
        ("goodbye", "Até mais"),
        (None, "Olá!"),
    ],
)
def test_small_talk_templates(app, kind, expected):
    response = turn(app, {"type": "small_talk", "kind": kind})
    assert expected in response.text
    assert app.provider.policy_requests == []


def test_complaint_acknowledges_without_claiming_registration(app):
    response = turn(app, {"type": "complaint", "description": "atraso"})
    text = response.text
    assert "Sinto muito" in text
    assert "nada foi registrado" in text
    for claim in ("registrei", "encaminhei", "foi registrada", "transferi"):
        assert claim not in text


def test_greeting_and_search_keep_source_order(app):
    response = turn(app, {"type": "small_talk", "kind": "greeting"}, search("Piano"))
    assert response.text.index("Olá!") < response.text.index("Piano")


class Transport:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def open(self, request, timeout):
        from io import BytesIO

        self.calls.append(request)
        return BytesIO(
            json.dumps({"done": True, "message": {"content": self.content}}).encode()
        )


def test_ollama_policy_call_uses_policy_schema_and_no_history():
    from emporio_da_musica.providers.base import PolicyRequest

    provider = OllamaProvider()
    provider.opener = Transport(json.dumps(HOURS))
    assert json.loads(provider.explain(PolicyRequest(question="Horário?"))) == HOURS
    body = json.loads(provider.opener.calls[0].data)
    assert set(body["format"]["properties"]) == {
        "covered",
        "answer",
        "policy_references",
    }
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "Rua 14 de Maio" in body["messages"][0]["content"]
    assert "Official policy explanation prompt" in body["messages"][0]["content"]


def test_uncovered_question_uses_scope_template_not_model_prose(app):
    app.provider.policy_responses.append(
        {"covered": False, "answer": "A capital é Paris.", "policy_references": ["1"]}
    )
    response = turn(app, policy("Qual a capital da França?"))
    assert response.results[0].operation == "out_of_scope"
    assert "Paris" not in response.text
    assert "foge do que eu consigo atender" in response.text


def test_uncovered_answer_may_omit_text_and_sections(app):
    app.provider.policy_responses.append({"covered": False})
    response = turn(app, policy("Qual a capital?"))
    assert response.results[0].operation == "out_of_scope"


def test_policy_call_receives_only_text_from_current_message(app):
    app.provider.policy_responses.append(HOURS)
    turn(app, policy("pedido 1 do cliente Fulano: qual o horário?"), message="horário?")
    assert app.provider.policy_requests[-1].question == "horário?"
    app.provider.policy_responses.append(HOURS)
    turn(
        app,
        policy("qual o horário de sábado"),
        message="Quanto custa o piano e qual o horário de sábado?",
    )
    assert app.provider.policy_requests[-1].question == "qual o horário de sábado"


def test_contact_request_is_answered_without_model(app):
    response = turn(
        app, policy("Qual o telefone?"), message="Qual o telefone de vocês?"
    )
    assert response.results[0].status == "requires_confirmation"
    assert "divergentes" in response.text
    assert app.provider.policy_requests == []


def test_store_name_and_manual_numbers_are_allowed(app):
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "No Empório da Música, trocas por defeito valem por 30 dias.",
            "policy_references": ["4.2"],
        }
    )
    response = turn(app, policy("troca?"))
    assert response.results[0].status == "success"
