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
    assert response.results[0].data.template == "accessory_redirect"


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
    assert "cordas" not in response.text


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


UNCOVERED = {"covered": False, "answer": "", "policy_references": []}


@pytest.mark.parametrize(
    "message",
    [
        "Qual o endereço da loja?",
        "Qual o endereço?",
        "Onde fica a loja?",
        "Onde vocês ficam?",
        "Vocês estão onde?",
        "Como faço pra chegar aí?",
        "Qual a rua da loja?",
    ],
)
@pytest.mark.parametrize("failure", [UNCOVERED, ProviderError("synthetic"), "not json"])
def test_uncovered_address_question_falls_back_to_manual(app, message, failure):
    app.provider.policy_responses.append(failure)
    response = turn(app, policy(message), message=message)
    result = response.results[0]
    assert result.status == "success"
    assert result.policy_references == ("1.2",)
    assert "Rua 14 de Maio, 3200" in response.text
    assert "seção 1.2" in response.text


@pytest.mark.parametrize(
    "message",
    [
        "Posso trocar o endereço de entrega?",
        "Onde fica o rastreio do pedido?",
        "Onde ficam as regras de devolução?",
        "Qual a localização do meu pedido?",
        "Como chego a pagar em 12x?",
        "Qual o prazo de troca e o endereço para devolver?",
    ],
)
def test_other_questions_are_not_address_requests(app, message):
    app.provider.policy_responses.append(UNCOVERED)
    response = turn(app, policy(message), message=message)
    assert "Rua 14 de Maio" not in response.text


def test_covered_answer_is_not_replaced_by_address(app):
    message = "Qual o endereço e o horário de sábado?"
    app.provider.policy_responses.extend([UNCOVERED, HOURS])
    response = turn(
        app,
        policy("Qual o endereço"),
        policy("o horário de sábado"),
        message=message,
    )
    assert len(app.provider.policy_requests) == 2
    assert response.text.count("Rua 14 de Maio") == 1
    assert "seção 2" in response.text


def test_contact_word_elsewhere_does_not_hide_policy_question(app):
    message = "Posso trocar por e-mail? Qual o prazo de troca por defeito?"
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "Trocas por defeito valem por 30 dias após a compra.",
            "policy_references": ["4.2"],
        }
    )
    response = turn(
        app,
        policy("Posso trocar por e-mail?"),
        policy("Qual o prazo de troca por defeito?"),
        message=message,
    )
    statuses = [r.status for r in response.results]
    assert statuses == ["requires_confirmation", "success"]
    assert response.text.count("divergentes") == 1
    assert "30 dias" in response.text


def test_contact_request_without_isolated_question_uses_message(app):
    response = turn(app, policy(), message="Qual o WhatsApp de vocês?")
    assert response.results[0].reason_code == "CONTACT_CONFLICT"
    assert app.provider.policy_requests == []


@pytest.mark.parametrize(
    "message",
    [
        "Qual o endereço da loja e o horário de sábado?",
        "Posso mudar o endereço de vocês no pedido?",
        "Vocês abrem sábado? E onde fica a loja?",
    ],
)
@pytest.mark.parametrize("failure", [UNCOVERED, ProviderError("synthetic")])
def test_mixed_question_never_becomes_only_the_address(app, message, failure):
    app.provider.policy_responses.append(failure)
    response = turn(app, policy(), message=message)
    assert "Rua 14 de Maio" not in response.text


def test_non_literal_question_does_not_take_the_address(app):
    message = "Qual o endereço da loja e o horário de funcionamento?"
    app.provider.policy_responses.extend([UNCOVERED, UNCOVERED])
    response = turn(
        app,
        policy("Quais são os horários?"),
        policy("Qual o endereço da loja?"),
        message=message,
    )
    assert response.text.count("Rua 14 de Maio") == 1
    assert response.results[0].operation == "out_of_scope"


def test_contact_request_not_isolated_still_gets_notice(app):
    app.provider.policy_responses.append(HOURS)
    response = turn(
        app, policy("Qual o horário?"), message="Qual o horário? E o telefone?"
    )
    assert [r.status for r in response.results] == [
        "success",
        "requires_confirmation",
    ]
    assert "divergentes" in response.text


def test_address_is_not_repeated_next_to_contact_notice(app):
    message = "Qual o telefone, qual o endereço da loja e qual o horário?"
    app.provider.policy_responses.extend([UNCOVERED, HOURS])
    response = turn(
        app,
        policy("qual o telefone"),
        policy("qual o endereço da loja"),
        policy("qual o horário"),
        message=message,
    )
    assert response.text.count("Rua 14 de Maio") == 1
    assert "divergentes" in response.text
    assert "seção 2" in response.text


@pytest.mark.parametrize(
    ("topic", "message", "template"),
    [
        ("cordas", "Vocês vendem cordas de nylon?", "accessory_redirect"),
        ("capas", "Tem capa pra violão?", "accessory_redirect"),
        (None, "Vocês têm amplificador?", "accessory_redirect"),
        ("futebol", "Quem ganhou a Copa de 2002?", "scope_redirect"),
        ("geografia", "Qual a capital da França?", "scope_redirect"),
    ],
)
def test_accessories_and_unrelated_topics_get_distinct_redirects(
    app, topic, message, template
):
    response = turn(app, {"type": "out_of_scope", "topic": topic}, message=message)
    assert response.results[0].data.template == template
    accessory = template == "accessory_redirect"
    assert ("exclusivamente com instrumentos" in response.text) is accessory
    assert "não indico outras lojas" in response.text or not accessory


@pytest.mark.parametrize(
    "text",
    [
        "violão de 7 cordas",
        "cordas orquestrais",
        "in case you know",
        "cabo do exército",
        "Cabo Frio",
        "capa do livro",
        "pedal de bateria",
        "previsão do tempo",
    ],
)
def test_non_accessory_wording_gets_general_redirect(app, text):
    response = turn(app, {"type": "out_of_scope", "topic": text}, message=text)
    assert response.results[0].data.template == "scope_redirect"


@pytest.mark.parametrize(
    "text",
    [
        "cordas de nylon",
        "jogo de cordas",
        "encordoamento",
        "palheta",
        "cabo para guitarra",
        "capa pra violão",
        "case de teclado",
        "pedais de efeito",
        "pedaleira",
        "amplificador",
    ],
)
def test_accessory_wording_gets_accessory_redirect(app, text):
    response = turn(app, {"type": "out_of_scope", "topic": text}, message=text)
    assert response.results[0].data.template == "accessory_redirect"


def test_accessory_word_of_another_intent_is_not_counted(app):
    response = turn(
        app,
        search("Piano"),
        {"type": "out_of_scope", "topic": "previsão do tempo"},
        message="O Piano tem pedais? E qual a previsão do tempo?",
    )
    assert response.results[-1].data.template == "scope_redirect"


def test_message_without_topic_is_used_only_for_single_request(app):
    message = "Vocês vendem palhetas? E o Piano?"
    response = turn(app, {"type": "out_of_scope"}, search("Piano"), message=message)
    assert response.results[0].data.template == "scope_redirect"
    response = turn(app, {"type": "out_of_scope"}, message="Vocês vendem palhetas?")
    assert response.results[0].data.template == "accessory_redirect"


def test_warranty_answer_does_not_mix_privacy_law_with_warranty(app):
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "A garantia dos instrumentos é de 90 dias contra defeitos de fabricação, conforme a Lei Geral de Proteção de Dados (LGPD).",
            "policy_references": ["8.1"],
        }
    )
    response = turn(app, policy(), message="Como funciona a garantia dos instrumentos?")
    assert "LGPD" not in response.text
    assert "90 dias" in response.text
    assert "recebimento" in response.text
    assert "certificado" in response.text


def test_warranty_summary_does_not_replace_mixed_policy_answer(app):
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "A garantia legal é de 90 dias. Aos sábados atendemos das 9h às 13h.",
            "policy_references": ["8.1", "2"],
        }
    )
    response = turn(app, policy(), message="Qual é a garantia e o horário de sábado?")
    assert "9h às 13h" in response.text
    assert response.results[0].policy_references == ("8.1", "2")


def test_warranty_summary_does_not_promise_manufacturer_specific_duration(app):
    app.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "Esse fabricante oferece 2 anos de garantia.",
            "policy_references": ["8.2"],
        }
    )
    response = turn(
        app, policy(), message="Qual é a garantia do fabricante do Yamaha C40?"
    )
    assert "2 anos" not in response.text
    assert "certificado" in response.text
    assert response.results[0].policy_references == ("8.1", "8.2", "8.3")
