"""Regressions for findings from the code, security, and diagnostic reviews."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from emporio_da_musica.cli import startup_warning
from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderRequest,
)
from emporio_da_musica.providers.ollama import OllamaProvider

from .support import FakeProvider, payment, turn

DEMO = Path(__file__).parent.parent / "data" / "demo"
OK = {"covered": True, "answer": "Texto.", "policy_references": ["3"]}


@pytest.fixture
def demo():
    return Controller(
        load_snapshot(DEMO),
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def search(query=None, category=None, **fields):
    return {"type": "product_search", "query": query, "category": category, **fields}


POLICY = {"type": "policy_question"}


# Item 1: model text marked as unsupported is never shown.
@pytest.mark.parametrize(
    "answer, refs, message",
    [
        ("Sim, 10% para professores.", ["6"], "dão desconto para professores?"),
        ("O voo abre às 10.", ["2"], "que horario abre o aeroporto?"),
        ("Compre na Loja X.", ["2"], "garantia estendida existe?"),
    ],
)
def test_uncovered_model_prose_is_never_displayed(demo, answer, refs, message):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": answer, "policy_references": refs}
    )
    text = turn(demo, POLICY, message=message).text
    assert answer not in text and "foge" in text


def test_uncovered_stacking_question_uses_reviewed_text(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "x", "policy_references": ["6"]}
    )
    text = turn(demo, POLICY, message="a promoção acumula com pix?").text
    assert "não são cumulativos" in text


def test_return_summary_includes_the_refund_period(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "10 dias.", "policy_references": ["4.1"]}
    )
    text = turn(demo, POLICY, message="qual o prazo do reembolso?").text
    assert "10 dias úteis" in text


# Item 2 and manual §7.3: unavailable products get no totals, but get alternatives.
def test_discontinued_product_gets_no_total_and_offers_alternatives(demo):
    product = next(
        p for p in demo.snapshot.products.values() if p.status == "discontinued"
    )
    response = turn(
        demo,
        payment(
            product_reference={"kind": "query", "query": product.name},
            quantity=1,
            payment_method="pix",
        ),
        message=f"quero {product.name} no pix",
    )
    assert response.results[-1].status == "unavailable"
    assert "Total" not in response.text and "Para continuar" not in response.text
    assert "disponíveis parecidas" in response.text


def test_out_of_stock_card_offers_alternatives(demo):
    text = turn(demo, search("GF-3D"), message="quero o Giannini GF-3D").text
    assert "disponíveis parecidas" in text
    alternatives = text.split("disponíveis parecidas:")[1]
    assert "GF-3D" not in alternatives


# Item 3: budget answer after the guided question.
@pytest.mark.parametrize("query", ["viola", "500", None])
def test_budget_after_guided_question_stays_in_category(demo, query):
    turn(demo, search(None, "Violões"), message="quero um violão")
    response = turn(demo, search(query, max_price_brl="500"), message="até 500 reais")
    assert response.results[0].status == "success"
    assert "Tagima Memphis" in response.text and "Rozini" in response.text


# Item 4: model names are not installments.
def test_model_name_with_x_keeps_pix(demo):
    response = turn(
        demo,
        payment(
            product_reference={"kind": "query", "query": "Yamaha Bass 3X"},
            quantity=1,
            payment_method="pix",
        ),
        message="quero o Yamaha Bass 3X, uma unidade no pix",
    )
    assert "R$ 10.872,75" in response.text


def test_real_installments_still_block_pix(demo):
    response = turn(
        demo,
        payment(
            product_reference={"kind": "query", "query": "Yamaha C70"},
            quantity=1,
            payment_method="pix",
        ),
        message="Yamaha C70 no pix ou em 3x",
    )
    assert response.results[-1].status == "needs_information"


# Items 5 and 6, and related promotion filters.
def test_other_model_of_the_brand_is_not_shown_as_promoted(demo):
    response = turn(demo, POLICY, message="o Crafter D-8 está em promoção?")
    assert "não está em promoção ativa" in response.text
    assert "HT-100" not in response.text


def test_promotion_search_respects_budget_and_quantity(demo):
    response = turn(
        demo,
        search(None, "Violões", max_price_brl="3000"),
        message="violão em promoção até 3000",
    )
    assert "Taylor" not in response.text and "Crafter" in response.text
    response = turn(
        demo, search(None, "Ukuleles", quantity=20), message="20 ukuleles em promoção"
    )
    assert "estoque insuficiente" in response.text


def test_promotion_word_does_not_hijack_several_searches(demo):
    response = turn(
        demo,
        search(None, "Ukuleles"),
        search("Fender"),
        message="ukulele em promoção e guitarra Fender",
    )
    assert "Telecaster" in response.text


def test_two_names_of_one_empty_category_have_no_promotion(demo):
    response = turn(demo, POLICY, message="tem teclados e pianos em promoção?")
    assert response.results[0].reason_code == "NO_ACTIVE_PROMOTION"


@pytest.mark.parametrize("message", ["mostre violão", "tem violão em promoção?"])
def test_singular_category_finds_products(demo, message):
    assert turn(demo, search(None, "Violão"), message=message).results[0].status == (
        "success"
    )


# Item 7.
@pytest.mark.parametrize(
    "message",
    [
        "tem algum instrumento de baixo custo?",
        "instrumentos com preços mais baixos",
        "quero algo de baixo preço",
    ],
)
def test_low_price_wording_is_not_a_bass(demo, message):
    response = turn(demo, search(), message=message)
    assert response.results[0].data.total_matches == 65


# Item 8.
@pytest.mark.parametrize(
    "message", ["e aí!", "oie", "salve", "beleza?", "como vai?", "boas"]
)
def test_common_greetings_stay_greetings(demo, message):
    intent = {"type": "small_talk", "kind": "greeting"}
    assert turn(demo, intent, message=message).results[0].operation == "small_talk"


# Item 9.
def test_failed_extraction_keeps_pending_query(demo):
    turn(
        demo,
        payment(product_reference={"kind": "query", "query": "Yamaha C40"}),
        message="quero o Yamaha C40",
    )
    assert demo.session.pending
    demo.provider.responses.append(ProviderError("repeat limit"))
    response = demo.handle("pagamento no pix")
    assert demo.session.pending and "interpretar" in response.text
    assert not demo.provider.policy_requests


# Item 10.
@pytest.mark.parametrize(
    "message",
    ["posso parcelar produto em promoção?", "produto em oferta tem garantia?"],
)
def test_policy_question_about_promoted_products_stays_policy(demo, message):
    demo.provider.policy_responses.append(OK)
    assert turn(demo, POLICY, message=message).results[0].operation == (
        "policy_question"
    )


# Item 11.
def test_identity_does_not_replace_other_questions(demo):
    demo.provider.policy_responses.append(OK)
    response = turn(
        demo,
        {"type": "small_talk", "kind": "greeting"},
        POLICY,
        message="quem é você? e vocês abrem domingo?",
    )
    assert "Texto." in response.text


# Item 12.
def test_product_with_two_active_promotions_does_not_crash(demo):
    product_id, promotions = next(
        (i, p) for i, p in demo.snapshot.promotions_by_product.items() if p
    )
    active = replace(promotions[0], is_active=True)
    demo.snapshot.promotions_by_product[product_id] = (active, active)
    response = turn(demo, POLICY, message="quais promoções vocês têm?")
    assert response.results[0].reason_code == "MULTIPLE_ACTIVE_PROMOTIONS"


# Security hardening.
@pytest.mark.parametrize(
    "answer",
    [
        "Telefone: ٦٧٩٩٩٩٩٩٩٩٩",
        "Fale pelo instagram da loja",
        "w​ww.lojax.c​om",
        "Solicitei seu estorno.",
        "Abri um chamado para você.",
    ],
)
def test_contact_and_action_guards(demo, answer):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": answer, "policy_references": ["2"]}
    )
    assert answer not in turn(demo, POLICY, message="como posso pagar?").text


def test_uncovered_hours_answer_uses_reviewed_text(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "Abrimos sempre.", "policy_references": ["2"]}
    )
    text = turn(demo, POLICY, message="vocês abrem domingo?").text
    assert "Abrimos sempre" not in text and "Domingos e feriados" in text


class Failing:
    def __init__(self, code):
        self.code = code

    def open(self, *args, **kwargs):
        raise HTTPError("u", self.code, "x", {}, BytesIO(b""))


@pytest.mark.parametrize("code", [302, 500])
def test_server_check_does_not_call_http_answers_unreachable(code):
    provider = OllamaProvider()
    provider.opener = Failing(code)
    assert provider.check_server() is None


def test_missing_model_during_session_is_a_service_problem():
    provider = OllamaProvider()
    provider.opener = Failing(404)
    with pytest.raises(ProviderConnectionError):
        provider.propose(ProviderRequest(message="x"))


def test_startup_warning_removes_control_characters():
    class Provider:
        model = "x\x1b]0;pwn\x07"

        def check_server(self):
            return "model_missing"

    assert "\x1b" not in startup_warning(Provider(), "u")


# Smaller conversation findings.
def test_card_with_known_quantity_asks_only_for_payment(demo):
    text = turn(demo, search("C70", quantity=2), message="2 C70").text
    assert "Quantas unidades" not in text and "como prefere pagar" in text.lower()


def test_list_line_shows_insufficient_stock(demo):
    text = turn(demo, search("Martin", quantity=5), message="5 violões Martin").text
    assert "estoque insuficiente" in text


def test_brand_answer_keeps_quantity(demo):
    turn(demo, search(None, "Violões"), message="quero um violão")
    response = turn(
        demo,
        payment(product_reference={"kind": "query", "query": "Yamaha"}, quantity=2),
        message="2 Yamaha",
    )
    assert response.results[0].data.products[0].quantity == 2


def test_guide_brands_only_include_sellable_products(demo):
    text = turn(demo, search(None, "Baixos"), message="quero um baixo").text
    assert "Ibanez" not in text


def test_accessory_of_outside_instrument_is_an_accessory(demo):
    response = turn(demo, POLICY, message="vocês vendem cordas de violino?")
    assert "acessórios" in response.text or response.results[0].operation != (
        "product_search"
    )


def test_return_of_outside_instrument_uses_policy(demo):
    demo.provider.policy_responses.append(OK)
    response = turn(demo, POLICY, message="posso devolver minha flauta?")
    assert response.results[0].operation == "policy_question"


# Search findings.
def test_name_words_out_of_order_or_apart_match(demo):
    response = turn(
        demo, search("Takamine GD20 Natural"), message="Takamine GD20 Natural"
    )
    assert "Takamine GD20" in response.text


def test_instrument_word_is_removed_from_quote_reference(demo):
    response = turn(
        demo,
        payment(
            product_reference={"kind": "query", "query": "ukulele Ohana CK-20"},
            quantity=1,
            payment_method="boleto",
        ),
        message="quero o ukulele Ohana CK-20, uma unidade no boleto",
    )
    assert response.results[-1].status == "success"


def test_misspelled_brand_is_corrected(demo):
    response = turn(demo, search("gianini", "Violões"), message="violão gianini")
    assert all("Giannini" in q.name for q in response.results[0].data.products)


def test_unknown_name_says_the_filter_was_dropped(demo):
    response = turn(demo, search("xyzabc", "Violões"), message="violão xyzabc")
    assert "Não encontrei esse nome" in response.text


def test_brand_sent_out_of_scope_is_searched(demo):
    intent = {"type": "out_of_scope", "topic": "takamine"}
    response = turn(demo, intent, message="tem takamine?")
    assert response.results[0].operation == "product_search"
    assert "Takamine" in response.text


@pytest.mark.parametrize(
    "fields", [{"payment_method": "credit"}, {"payment_method": None}]
)
def test_installment_count_question_gets_the_maximum(demo, fields):
    turn(demo, search("Tagima Memphis"), message="Quero o Tagima Memphis")
    response = turn(
        demo,
        payment(product_reference={"kind": "selected"}, quantity=None, **fields),
        message="aceita parcelar em quantas vezes?",
    )
    assert "até 5x" in response.text
    assert Decimal("429.90") == response.results[-1].data.final_total_brl


# Findings from the re-review.
@pytest.mark.parametrize(
    "query, message, expected",
    [
        (None, "agora quero um ukulele", "Ukuleles"),
        ("guitarra", "na verdade quero guitarra", "Guitarras"),
    ],
)
def test_new_instrument_replaces_the_guided_one(demo, query, message, expected):
    turn(demo, search(None, "Violões"), message="quero comprar um violao")
    assert expected in turn(demo, search(query), message=message).text


def test_new_instrument_and_brand_replace_the_guided_one(demo):
    turn(demo, search(None, "Violões"), message="quero comprar um violao")
    text = turn(
        demo, search("guitarra Fender"), message="na verdade guitarra Fender"
    ).text
    assert "Telecaster" in text


def test_combined_payment_question_is_not_a_stacking_question(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "Acima de R$ 2.000,00.", "policy_references": ["3"]}
    )
    text = turn(demo, POLICY, message="posso somar pix e cartão no pagamento?").text
    assert "cumulativos" not in text


@pytest.mark.parametrize("method", ["pix", "boleto", "debit"])
def test_installment_question_keeps_another_method(demo, method):
    word = {"pix": "pix", "boleto": "boleto", "debit": "debito"}[method]
    response = turn(
        demo,
        payment(
            product_reference={"kind": "query", "query": "Taylor 110e"},
            quantity=None,
            payment_method=method,
        ),
        message=f"quantas vezes no {word} o Taylor 110e?",
    )
    assert "(crédito)" not in response.text


@pytest.mark.parametrize(
    "message",
    [
        "a garantia tem cobertura para as cordas?",
        "tem garantia para saxofone?",
        "tem troca de palheta de sopro?",
    ],
)
def test_policy_question_mentioning_a_product_type_stays_policy(demo, message):
    demo.provider.policy_responses.append(OK)
    assert turn(demo, POLICY, message=message).results[0].operation == (
        "policy_question"
    )


def test_number_does_not_match_inside_a_model_name(demo):
    response = turn(demo, search("Yamaha 8"), message="tem Yamaha 8?")
    assert response.results[0].status == "not_found"


@pytest.mark.parametrize("word", ["preco", "tender", "estudo", "musica"])
def test_ordinary_words_are_not_spelling_corrected(demo, word):
    response = turn(demo, search(word), message=word)
    assert response.results[0].status == "not_found"


def test_answer_mentioning_a_channel_is_kept(demo):
    demo.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "O código vai por e-mail.",
            "policy_references": ["5"],
        }
    )
    assert (
        "vai por e-mail" in turn(demo, POLICY, message="como recebo o rastreio?").text
    )


def test_unknown_model_of_a_promoted_brand_has_no_promotion(demo):
    response = turn(demo, POLICY, message="o Taylor Zeta tem promoção?")
    assert response.results[0].reason_code == "NO_ACTIVE_PROMOTION"


def test_other_service_hours_are_not_answered_with_store_hours(demo):
    demo.provider.policy_responses.append(
        {"covered": False, "answer": "x", "policy_references": ["2"]}
    )
    assert "foge" in turn(demo, POLICY, message="o correio funciona sabado?").text


def test_hours_summary_mentions_special_dates(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "x", "policy_references": ["2"]}
    )
    assert (
        "datas especiais"
        in turn(demo, POLICY, message="voces abrem na black friday?").text
    )


# Manual testing: selecting from the list.
def list_drums(demo):
    return turn(demo, search("bateria"), message="quero comprar uma bateria")


@pytest.mark.parametrize("message", ["3", "o 3", "número 3", "opção 3", "3º"])
def test_bare_list_number_selects_without_the_model(demo, message):
    list_drums(demo)
    response = demo.handle(message)
    assert "Yamaha Kit 3" in response.text and "Formas de pagamento" in response.text
    assert len(demo.provider.requests) == 1


def test_number_outside_the_list_goes_to_the_model(demo):
    list_drums(demo)
    demo.provider.responses.append({"intents": [search("bateria")]})
    demo.handle("9")
    assert len(demo.provider.requests) == 2


def test_number_answering_a_quantity_question_is_not_a_position(demo):
    list_drums(demo)
    demo.handle("1")
    assert "quantity" in demo.session.pending[0].requested_fields
    demo.provider.responses.append(
        {
            "pending_id": demo.session.pending[0].pending_id,
            "update": {"type": "payment_options", "quantity": 2},
        }
    )
    demo.handle("2")
    assert len(demo.provider.requests) == 2


@pytest.mark.parametrize(
    "message, expected",
    [
        ("bateria acustica yamaha kit 1 studio, pix", "R$ 4.217,05"),
        ("yamaha kit 3, pix", "R$ 14.175,90"),
    ],
)
def test_typed_name_overrides_an_invented_selection(demo, message, expected):
    list_drums(demo)
    response = turn(
        demo,
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
        message=message,
    )
    assert expected in response.text


def test_selection_is_kept_when_no_name_is_typed(demo):
    turn(demo, search("Yamaha C70"), message="Yamaha C70")
    response = turn(
        demo,
        payment(
            product_reference={"kind": "selected"}, quantity=1, payment_method="pix"
        ),
        message="esse, uma unidade no pix",
    )
    assert "R$ 806,55" in response.text


@pytest.mark.parametrize("message", ["1 unidade", "1", "uma unidade, 1 no pix"])
def test_quantity_number_does_not_change_the_selected_product(demo, message):
    list_drums(demo)
    demo.handle("3")
    pending = demo.session.pending
    demo.provider.responses.append(
        {"intents": [payment(product_reference={"kind": "selected"}, quantity=1)]}
    )
    response = demo.handle(message)
    assert "Kit 1" not in response.text
    assert pending


def test_freight_confirmation_does_not_add_a_product_card(demo):
    intent = {
        "type": "shipping_quote",
        "product_reference": {"kind": "query", "query": "Takamine GD20"},
        "quantity": 1,
        "destination": {"city": "Dourados", "state": "MS"},
        "payment_method": "boleto",
    }
    response = turn(
        demo, intent, message="frete do Takamine GD20 no boleto para Dourados"
    )
    assert [r.operation for r in response.results] == ["shipping_quote"]
    assert "Formas de pagamento" not in response.text
