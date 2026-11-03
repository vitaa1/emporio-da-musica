"""Broad requests are guided; a chosen model shows stock, price, and payment."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot

from .support import FakeProvider, payment, turn

DEMO = Path(__file__).parent.parent / "data" / "demo"


@pytest.fixture
def demo():
    return Controller(
        load_snapshot(DEMO),
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def search(query=None, category=None, **fields):
    return {"type": "product_search", "query": query, "category": category, **fields}


@pytest.mark.parametrize("message", ["quero comprar um violão", "violao"])
def test_broad_request_asks_for_preference_instead_of_listing(demo, message):
    response = turn(demo, search(None, "Violões"), message=message)
    assert "marca" in response.text and "Yamaha" in response.text
    assert "35" in response.text and "1. " not in response.text
    assert response.results[0].data.total_matches == 35
    assert demo.session.displayed_product_ids == ()


def test_explicit_listing_is_not_replaced_by_a_question(demo):
    response = turn(demo, search(None, "Violões"), message="mostre os violões")
    assert "1. Yamaha C40" in response.text


def test_list_is_short_and_asks_which_model(demo):
    response = turn(demo, search("Yamaha", "Violões"), message="violões yamaha")
    first = response.text.splitlines()[0]
    assert first == "1. Yamaha C40 Nylon Natural — R$ 599,90"
    assert "Qual modelo" in response.text


def test_answer_after_guidance_stays_in_the_category(demo):
    turn(demo, search(None, "Violões"), message="quero um violão")
    response = turn(demo, search("Yamaha"), message="yamaha")
    assert "Bass" not in response.text and "Bateria" not in response.text
    assert "Yamaha C40" in response.text


def test_chosen_model_shows_stock_price_and_every_payment(demo):
    response = turn(demo, search("C70"), message="quero o C70")
    text = response.text
    product = next(p for p in demo.snapshot.products.values() if "C70" in p.name)
    assert f"Em estoque: {product.stock_quantity} unidade(s)" in text
    assert "Preço por unidade: R$ 849,00" in text
    assert "PIX: R$ 806,55 (5% de desconto)" in text
    assert "Débito: R$ 849,00" in text and "Boleto: R$ 849,00" in text
    assert "Crédito: até 8x sem juros" in text


def test_promotion_card_does_not_stack_pix(demo):
    text = turn(demo, search("Crafter HT-100"), message="quero o Crafter HT-100").text
    assert "Promoção ativa: 18%" in text
    assert "PIX: R$ 1.967,18 (sem desconto adicional" in text


def test_unavailable_model_offers_no_payment(demo):
    product = next(p for p in demo.snapshot.products.values() if p.status != "active")
    text = turn(demo, search(product.name), message=f"quero o {product.name}").text
    assert "indisponível" in text and "Formas de pagamento" not in text


def test_ordinal_choice_without_facts_shows_card_and_asks(demo):
    turn(demo, search("Yamaha", "Violões"), message="violões yamaha")
    response = turn(
        demo,
        payment(product_reference={"kind": "ordinal", "ordinal": 2}, quantity=None),
        message="quero o segundo",
    )
    assert "Yamaha C70" in response.text and "Formas de pagamento" in response.text
    assert "Para continuar" in response.text


def test_requested_payment_still_gives_the_exact_quote(demo):
    response = turn(
        demo, search("C70", quantity=2, payment_method="pix"), message="2 C70 no pix"
    )
    assert "R$ 1.613,10" in response.text and "Formas de pagamento" not in response.text


def test_card_keeps_positions_of_the_current_list(demo):
    turn(demo, search("Yamaha", "Violões"), message="violões yamaha")
    listed = demo.session.displayed_product_ids
    turn(
        demo,
        payment(product_reference={"kind": "ordinal", "ordinal": 2}, quantity=None),
        message="quero o segundo",
    )
    assert demo.session.displayed_product_ids == listed


def test_brand_answer_proposed_as_quote_still_filters_the_category(demo):
    turn(demo, search(None, "Violões"), message="quero um violão")
    response = turn(
        demo,
        payment(product_reference={"kind": "query", "query": "Yamaha"}, quantity=None),
        message="yamaha",
    )
    assert "Bass" not in response.text and "Yamaha C40" in response.text
    assert "Para continuar" not in response.text


def test_instrument_request_sent_out_of_scope_is_searched(demo):
    intent = {"type": "out_of_scope", "topic": "guitarras"}
    response = turn(demo, intent, message="mostre as guitarras")
    assert response.results[0].operation == "product_search"
    assert response.results[0].status == "success"


@pytest.mark.parametrize(
    "message", ["quero cordas de guitarra", "qual a capital da frança?"]
)
def test_real_out_of_scope_messages_stay_out_of_scope(demo, message):
    intent = {"type": "out_of_scope", "topic": message}
    assert turn(demo, intent, message=message).results[0].operation == "out_of_scope"


def test_payment_message_does_not_show_the_card(demo):
    turn(demo, search("C70"), message="C70")
    response = turn(
        demo,
        payment(product_reference={"kind": "selected"}, quantity=1),
        message="não quero pix, quanto fica?",
    )
    assert "Formas de pagamento" not in response.text


@pytest.mark.parametrize(
    "intent, message",
    [
        (search("R$ 1000", max_price_brl="1000"), "violões até R$ 1000"),
        (
            search("viola", "Violões", max_price_brl="1000"),
            "Quais violões até R$ 1000?",
        ),
        (search("viola", max_price_brl="800"), "quero um violão até 800"),
        (search("800", max_price_brl="800"), "quero um violão até 800"),
    ],
)
def test_budget_search_keeps_the_typed_instrument(demo, intent, message):
    response = turn(demo, intent, message=message)
    assert response.results[0].status == "success"
    assert "1. " in response.text


def test_adjective_query_recovers_typed_brand(demo):
    response = turn(demo, search("barato", "Violões"), message="violao yamaha barato")
    assert "Yamaha C40" in response.text and "Tagima" not in response.text


def test_accessory_search_proposed_by_model_is_out_of_scope(demo):
    response = turn(
        demo, search("cords", "Guitarras"), message="quero cordas de guitarra"
    )
    assert response.results[0].operation == "out_of_scope"
    assert "acessórios" in response.text


def test_copied_budget_is_dropped_silently_when_no_budget_was_mentioned(demo):
    response = turn(
        demo, search("C70", max_price_brl="1000"), message="quanto custa o C70?"
    )
    assert "limite de preço" not in response.text


def test_bass_is_an_instrument_but_a_low_price_is_not(demo):
    response = turn(demo, search("baixo"), message="quero um baixo")
    assert response.results[0].status == "success"
    assert response.results[0].data.total_matches == 4
    response = turn(
        demo, search(None, "Violões"), message="mostre violões de preço mais baixo"
    )
    assert response.results[0].data.total_matches == 35
    response = turn(demo, search(), message="mostre o preço mais baixo")
    assert response.results[0].data.total_matches == 65


def test_two_word_brand_is_shown_in_full(demo):
    response = turn(demo, search("baixo"), message="quero um baixo")
    assert "Music Man" in response.text
