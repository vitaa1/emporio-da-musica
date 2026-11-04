"""Store manual rules checked against the bundled demonstration data."""

import io
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from emporio_da_musica.cli import run_cli
from emporio_da_musica.composer import after_hours_notice
from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot

from .support import FakeProvider, payment, search, turn

POLICY = {"type": "policy_question"}
STORE = ZoneInfo("America/Campo_Grande")


@pytest.fixture
def demo():
    return Controller(
        load_snapshot(Path(__file__).parent.parent / "data/demo"),
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 3, 15, tzinfo=timezone.utc),
    )


def quote(name, **fields):
    return payment(
        product_reference={"kind": "query", "query": name}, quantity=1, **fields
    )


# §6.2: promotional prices appear with the original price and the percentage.
def test_promotion_list_shows_original_price_and_percent(demo):
    text = turn(demo, POLICY, message="quais promoções vocês têm?").text
    assert "R$ 1.967,18 (de R$ 2.399,00, promoção de 18%)" in text


def test_product_list_shows_original_price_of_promoted_item(demo):
    text = turn(demo, search("Ohana"), message="mostre ukuleles Ohana").text
    assert "R$ 439,20 (de R$ 549,00, promoção de 20%)" in text
    assert "R$ 249,90\n" in text


def test_alternatives_show_original_price_of_promoted_item():
    from decimal import Decimal

    from emporio_da_musica.composer import render_alternatives
    from emporio_da_musica.contracts.results import ProductQuote

    promoted = ProductQuote(
        product_id=1,
        name="Modelo",
        quantity=1,
        availability="available",
        list_unit_price_brl=Decimal("100.00"),
        promotion_percent=Decimal("10"),
        payment_method=None,
        installments=None,
        final_total_brl=Decimal("90.00"),
    )
    assert "(R$ 90,00, de R$ 100,00, promoção de 10%)" in render_alternatives(
        [promoted]
    )


# §7.3: an inactive promotion is stated, with the current price.
def test_product_without_active_promotion_shows_current_price(demo):
    response = turn(demo, POLICY, message="o Crafter D-8 está em promoção?")
    assert "não está em promoção ativa" in response.text
    assert "R$ 4.599,00" in response.text
    assert "HT-100" not in response.text
    assert "promoção de" not in response.text


def test_expired_campaign_for_product_is_not_promised(demo):
    text = turn(
        demo, POLICY, message="o Crafter CE-15 está na promoção de black friday?"
    ).text
    assert "A promoção Black Friday não está ativa" in text
    assert "R$ 3.899,00" in text


def test_expired_campaign_says_so_before_other_promotions(demo):
    text = turn(demo, POLICY, message="a black friday ainda está valendo?").text
    assert text.startswith("A promoção Black Friday não está ativa")
    assert "Estas são as promoções ativas agora:" in text
    assert "Crafter HT-100" in text


def test_active_campaign_lists_only_its_products(demo):
    text = turn(demo, POLICY, message="o que tem na oferta especial?").text
    assert "Kalani KAL-700T" in text
    assert "não está ativa" not in text
    assert "Crafter HT-100" not in text


def test_campaign_of_another_product_does_not_apply(demo):
    # Crafter HT-100 is promoted under "Desconto Exclusivo", not Black Friday.
    text = turn(demo, POLICY, message="o Crafter HT-100 tem black friday?").text
    assert "A promoção Black Friday não está ativa" in text


# §7.1: outside regular hours, the assistant says when the team returns.
@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 11, 3, 9, 0), None),  # Tuesday opening.
        (datetime(2026, 11, 3, 17, 59), None),
        (datetime(2026, 11, 7, 12, 59), None),  # Saturday.
        (datetime(2026, 11, 3, 8, 59), "hoje às 9h"),
        (datetime(2026, 11, 3, 18, 0), "amanhã às 9h"),
        (datetime(2026, 11, 6, 18, 0), "amanhã às 9h"),  # Friday to Saturday.
        (datetime(2026, 11, 7, 13, 0), "segunda às 9h"),  # Saturday, skips Sunday.
        (datetime(2026, 11, 8, 10, 0), "amanhã às 9h"),  # Sunday.
    ],
)
def test_after_hours_notice_boundaries(moment, expected):
    notice = after_hours_notice(moment.replace(tzinfo=STORE))
    if expected is None:
        assert notice is None
    else:
        assert expected in notice and "se não for feriado" in notice


def _cli_output(demo, moment):
    demo.clock = lambda: moment.replace(tzinfo=STORE)
    output = io.StringIO()
    run_cli(demo, io.StringIO(""), output)
    return output.getvalue()


def test_cli_shows_after_hours_notice_only_when_closed(demo):
    assert "fora do horário" in _cli_output(demo, datetime(2026, 11, 3, 22, 0))
    assert "fora do horário" not in _cli_output(demo, datetime(2026, 11, 3, 10, 0))


# §8.2: the manufacturer warranty range is stated.
def test_warranty_answer_states_manufacturer_range(demo):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "Varia.", "policy_references": ["8.2"]}
    )
    text = turn(demo, POLICY, message="qual o prazo da garantia do fabricante?").text
    assert "6 meses a 2 anos" in text and "90 dias" in text


# §3.1: combined payment states the BRL 2,000 threshold.
def test_combined_payment_below_threshold_is_not_offered(demo):
    response = turn(
        demo,
        quote("Kalani KAL-700T", payment_method="combined"),
        message="Kalani KAL-700T pagamento combinado",
    )
    assert response.results[-1].reason_code == "COMBINED_PAYMENT_BELOW_MINIMUM"
    assert "acima de R$ 2.000,00" in response.text
    assert "esse valor não passa disso" in response.text


def test_combined_payment_above_threshold_needs_only_split_confirmation(demo):
    response = turn(
        demo,
        quote("Taylor 110e", payment_method="combined"),
        message="Taylor 110e pagamento combinado",
    )
    assert response.results[-1].reason_code == "COMBINED_PAYMENT_REQUIRES_CONFIRMATION"
    assert "acima de R$ 2.000,00" in response.text


# §3.1: 2–3 installments are quoted when every reading of the rule allows them.
def test_small_band_quoted_when_every_reading_allows(demo):
    response = turn(
        demo,
        quote("Taylor 110e", payment_method="credit", installments=3),
        message="Taylor 110e em 3x no crédito",
    )
    assert response.results[-1].status == "success"
    assert "1ª parcela de R$ 1.839,70 e 2 de R$ 1.839,69" in response.text


def test_small_band_below_safe_minimum_requires_confirmation(demo):
    response = turn(
        demo,
        quote("Kalani KAL-700T", payment_method="credit", installments=3),
        message="Kalani KAL-700T em 3x no crédito",
    )
    assert response.results[-1].status == "success"  # R$ 107,70 each.
    response = turn(
        demo,
        quote("Ohana SK-10", payment_method="credit", installments=3),
        message="Ohana SK-10 em 3x no crédito",
    )
    assert response.results[-1].reason_code == "AMBIGUOUS_INSTALLMENT_BAND"


# Review findings: a campaign word alone is not a question about a promotion.
@pytest.mark.parametrize(
    "message",
    ["a loja vai estar aberta na páscoa?", "quando é a semana do músico?"],
)
def test_campaign_word_does_not_hijack_policy_question(demo, message):
    demo.provider.policy_responses.append(
        {"covered": True, "answer": "Veja o manual.", "policy_references": ["2"]}
    )
    assert "A promoção" not in turn(demo, POLICY, message=message).text


def test_campaign_word_does_not_hide_catalog(demo):
    response = turn(
        demo,
        {"type": "product_search", "category": "Violões"},
        message="mostre violões pra dar de presente na páscoa",
    )
    assert response.results[0].data.total_matches == 35


@pytest.mark.parametrize(
    "message", ["a black friday vale no pix?", "qual o desconto da black friday?"]
)
def test_campaign_status_comes_from_records_not_the_model(demo, message):
    text = turn(demo, POLICY, message=message).text
    assert text.startswith("A promoção Black Friday não está ativa")


def test_model_cannot_assert_a_campaign_is_active(demo):
    demo.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "A Black Friday está ativa com 90% de desconto.",
            "policy_references": ["6"],
        }
    )
    text = turn(demo, POLICY, message="como funciona a black friday?").text
    assert "90%" not in text


def test_model_may_explain_the_campaign_calendar(demo):
    demo.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "A Black Friday acontece em novembro.",
            "policy_references": ["6.1"],
        }
    )
    text = turn(demo, POLICY, message="a black friday é em novembro?").text
    assert "acontece em novembro" in text


def test_two_inactive_campaigns_are_both_stated(demo):
    text = turn(demo, POLICY, message="tem black friday e queima de estoque?").text
    assert "Black Friday não está ativa" in text
    assert "Queima de Estoque não está ativa" in text


def test_unknown_campaign_list_is_labeled_as_active_promotions(demo):
    text = turn(demo, POLICY, message="tem promoção de natal?").text
    assert text.startswith("Estas são as promoções ativas agora:")


def test_campaign_active_elsewhere_is_not_called_inactive(demo):
    text = turn(demo, POLICY, message="o Yamaha C70 está na oferta especial?").text
    assert "não vale para esse pedido" in text
    assert "não está ativa" not in text


def test_notice_is_plural_for_several_products(demo):
    text = turn(demo, POLICY, message="tem promoção da Yamaha?").text
    assert text.startswith("Esses produtos não estão em promoção ativa agora.")


def test_notice_promises_no_price_for_discontinued_product(demo):
    text = turn(demo, POLICY, message="o Shelby SN-7C está em promoção?").text
    assert "O preço atual" not in text and "descontinuado" in text


def test_brand_followed_by_campaign_keeps_notice(demo):
    text = turn(demo, POLICY, message="Crafter black friday tem?").text
    assert "Black Friday não está ativa" in text


def test_combined_without_quantity_does_not_refuse(demo):
    response = turn(
        demo,
        {
            "type": "product_search",
            "query": "Kalani KAL-700T",
            "payment_method": "combined",
        },
        message="Kalani KAL-700T pagamento combinado",
    )
    assert response.results[0].reason_code == "COMBINED_PAYMENT_REQUIRES_CONFIRMATION"


def test_card_offers_small_band_when_safe(demo):
    text = turn(demo, search("Ohana SK-10"), message="quero ver o Ohana SK-10").text
    assert "Crédito: até 2x sem juros" in text


# Bug hunt findings.
@pytest.mark.parametrize("message", ["promoção Taylor 110e em 2x", "tem oferta em 3x?"])
def test_installment_count_is_not_a_product_name(demo, message):
    text = turn(demo, POLICY, message=message).text
    assert "Taylor 110e" in text and "8%" in text


def test_combined_with_missing_or_unavailable_product_says_so(demo):
    text = turn(
        demo,
        {
            "type": "product_search",
            "query": "Inexistente XPTO",
            "payment_method": "combined",
        },
        message="busca Inexistente XPTO pagamento combinado",
    ).text
    assert "2.000" not in text
    text = turn(
        demo,
        quote("Giannini GF-3D", payment_method="combined"),
        message="Giannini GF-3D pagamento combinado",
    ).text
    assert "2.000" not in text


def test_product_on_campaign_question_checks_records(demo):
    text = turn(demo, POLICY, message="o Fender Telecaster está na black friday?").text
    assert "Black Friday não está ativa" in text and "R$ 5.400,00" in text


def test_calendar_answer_with_month_before_percent_is_shown(demo):
    demo.provider.policy_responses.append(
        {
            "covered": True,
            "answer": "A Black Friday acontece em novembro, com descontos de 15% a 30%.",
            "policy_references": ["6.1"],
        }
    )
    text = turn(demo, POLICY, message="a black friday é em novembro mesmo?").text
    assert "acontece em novembro" in text


def test_every_campaign_including_easter_is_reported(demo):
    text = turn(demo, POLICY, message="black friday e páscoa estão valendo?").text
    assert "Black Friday não está ativa" in text
    assert "de Páscoa não está ativa" in text


def test_short_model_word_keeps_current_price(demo):
    text = turn(demo, POLICY, message="promoção da Gibson Les Paul").text
    assert "não está em promoção ativa" in text and "R$ 18.900,00" in text


def test_instrument_outside_catalog_gets_no_promotion_list(demo):
    response = turn(demo, POLICY, message="tem promoção de saxofone?")
    assert response.results[0].reason_code == "NO_ACTIVE_PROMOTION"


@pytest.mark.parametrize("message", ["tem liquidação?", "black friday"])
def test_bare_campaign_search_does_not_dump_catalog(demo, message):
    response = turn(demo, {"type": "product_search"}, message=message)
    assert response.results[0].data.total_matches <= 4


@pytest.mark.parametrize(
    "message",
    [
        "Gibson Les Paul, pix + cartão",
        "Gibson Les Paul metade no pix e metade no cartão",
    ],
)
def test_manual_example_of_combined_payment_is_recognized(demo, message):
    text = turn(
        demo, quote("Gibson Les Paul", payment_method="combined"), message=message
    ).text
    assert "acima de R$ 2.000,00" in text


# Live matrix findings: clear requests do not depend on the model.
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("aceita boleto?", "3 dias úteis"),
        ("quantas vezes posso parcelar?", "12x"),
        ("como é o reembolso?", "10 dias úteis"),
        ("quem paga o frete da devolução?", "por conta da loja"),
        ("boquilha de sax pode trocar?", "higiene"),
        ("quanto tempo demora o sedex?", "2 a 5"),
        ("o produto chegou avariado, o que faço?", "recuse"),
        ("se o produto em promoção acabar, vocês seguram o preço?", "reserva de preço"),
        ("quando é a black friday?", "novembro"),
        ("quero excluir meus dados", "nada foi excluído"),
    ],
)
def test_clear_questions_use_reviewed_text_without_model(demo, message, expected):
    text = demo.handle(message).text
    assert expected in text
    assert not demo.provider.requests and not demo.provider.policy_requests


@pytest.mark.parametrize(
    "message",
    [
        "quero um amplificador para minha guitarra",
        "tem pedal de distorção?",
        "preciso de um cabo P10",
    ],
)
def test_accessory_requests_get_the_store_scope_message(demo, message):
    assert "exclusivamente" in demo.handle(message).text


def test_bare_instrument_question_searches_catalog(demo):
    assert demo.handle("tem bateria?").results[0].data.total_matches == 3


@pytest.mark.parametrize(
    "message",
    ["1 Yamaha C40 no boleto aceita?", "aceita boleto? e quanto custa o violão?"],
)
def test_specific_or_mixed_messages_still_use_the_model(demo, message):
    demo.provider.responses.append(
        {"intents": [{"type": "small_talk", "kind": "thanks"}]}
    )
    demo.handle(message)
    assert demo.provider.requests


def test_installments_above_limit_are_stated(demo):
    text = turn(
        demo,
        quote("Taylor 110e", payment_method="credit", installments=12),
        message="1 Taylor 110e em 13x no crédito",
    ).text
    assert "vai até 12x" in text


@pytest.mark.parametrize(
    "message",
    [
        "1 Gibson Les Paul parte no pix e parte no cartão",
        "1 Gibson Les Paul metade no pix",
    ],
)
def test_split_wording_is_combined_even_if_model_misses_it(demo, message):
    response = turn(demo, quote("Gibson Les Paul"), message=message)
    assert "acima de R$ 2.000,00" in response.text


def test_pix_or_card_question_is_not_combined(demo):
    response = turn(
        demo, quote("Gibson Les Paul"), message="1 Gibson Les Paul no pix ou no cartão?"
    )
    assert "acima de R$ 2.000,00" not in response.text


# Freight naming a product and a city does not depend on the model.
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("frete de 1 Yamaha C40 no pix para Campo Grande/MS", "frete grátis"),
        ("quanto é o frete de 1 Ohana SK-10 no pix para Campo Grande/MS?", "35,00"),
        ("frete de 1 Yamaha C40 no pix para Dourados/MS", "PAC"),
        ("frete de 1 Yamaha C40 no pix para São Paulo/SP", "PAC"),
        (
            "frete de uma unidade do Takamine GD20 no pix para Campo Grande MS?",
            "grátis",
        ),
        ("frete do Takamine GD20 no boleto para Dourados MS", "PAC"),
    ],
)
def test_freight_with_product_and_city(demo, message, expected):
    assert expected in demo.handle(message).text
    assert not demo.provider.requests


def test_freight_missing_payment_asks_only_for_it(demo):
    text = demo.handle("frete de 1 Yamaha C40 para Campo Grande/MS").text
    assert "forma de pagamento" in text
    assert "a quantidade" not in text and "o produto" not in text


def test_general_freight_question_states_the_region(demo):
    text = demo.handle("como funciona o frete para outras cidades?").text
    assert "região metropolitana" in text and "PAC" in text


def test_freight_without_identified_product_uses_the_model(demo):
    demo.provider.responses.append(
        {"intents": [{"type": "small_talk", "kind": "thanks"}]}
    )
    demo.handle("qual o frete para Dourados/MS?")
    assert demo.provider.requests
