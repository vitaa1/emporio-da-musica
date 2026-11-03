"""Search terms from the model are checked against what the customer typed."""

import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

import pytest

from emporio_da_musica.cli import startup_warning
from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderRequest,
)
from emporio_da_musica.providers.demo import DemoProvider
from emporio_da_musica.providers.ollama import OllamaProvider

from .support import FakeProvider, turn

DEMO = Path(__file__).parent.parent / "data" / "demo"


@pytest.fixture
def demo():
    return Controller(
        load_snapshot(DEMO),
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def search(query=None, category=None):
    return {"type": "product_search", "query": query, "category": category}


def names(response):
    return [q.name for q in response.results[0].data.products]


@pytest.mark.parametrize(
    "intent, message",
    [
        (search("viola", "Violões"), "estou querendo comprar um violao"),
        (search("viola"), "violao"),
        (search("violão"), "quero um violão"),
        (search("violões", "Violões"), "quais violões vocês têm?"),
        (search(), "quero um violao"),
    ],
)
def test_unaccented_or_invented_instrument_lists_the_category(demo, intent, message):
    response = turn(demo, intent, message=message)
    assert response.results[0].status == "success"
    assert response.results[0].data.total_matches == 35


def test_explicit_viola_is_not_replaced_by_acoustic_guitars(demo):
    response = turn(demo, search("viola"), message="vocês têm viola?")
    assert response.results[0].status == "not_found"


def test_typed_brand_lost_by_model_is_recovered(demo):
    response = turn(demo, search(None, "Violões"), message="liste os violoes da yamaha")
    assert names(response)
    assert all("Yamaha" in name for name in names(response))


def test_brand_kept_when_category_is_inferred_from_a_typed_word(demo):
    response = turn(demo, search(None, None), message="violoes da yamaha")
    assert all("Yamaha" in name for name in names(response))


def test_two_possible_filters_are_not_guessed(demo):
    response = turn(demo, search(None, "Violões"), message="violao yamaha ou tagima")
    assert response.results[0].data.total_matches == 35


def test_two_instruments_do_not_pick_a_category(demo):
    response = turn(demo, search(), message="violao ou guitarra")
    assert response.results[0].data.total_matches == 65


def test_alias_ignored_when_snapshot_lacks_that_category(app):
    response = turn(app, search("violão"), message="quero violão")
    assert response.results[0].data.total_matches == 2


class Refused:
    def open(self, *args, **kwargs):
        raise URLError("refused")


def test_unreachable_server_raises_connection_error():
    provider = OllamaProvider()
    provider.opener = Refused()
    with pytest.raises(ProviderConnectionError, match="^Ollama request failed$"):
        provider.propose(ProviderRequest(message="test"))


def test_unreachable_model_is_not_reported_as_misunderstanding(demo):
    demo.provider.responses.append(ProviderConnectionError("secret"))
    response = demo.handle("violao")
    assert "interpretar" not in response.text and "secret" not in response.text
    assert "indisponível" in response.text


def test_other_provider_failures_keep_the_generic_message(demo):
    demo.provider.responses.append(ProviderError("secret"))
    assert "interpretar" in demo.handle("violao").text


class Tags:
    def __init__(self, body):
        self.body = body
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return io.BytesIO(self.body)


def checked(opener, model="qwen2.5:3b"):
    provider = OllamaProvider(model=model)
    provider.opener = opener
    return provider.check_server()


def test_server_check_finds_installed_model_with_a_short_read_only_request():
    opener = Tags(b'{"models":[{"name":"qwen2.5:3b"}]}')
    assert checked(opener) is None
    request, timeout = opener.requests[0]
    assert request.full_url.endswith("/api/tags") and request.data is None
    assert timeout <= 5


def test_server_check_accepts_implicit_latest_tag():
    assert checked(Tags(b'{"models":[{"name":"m:latest"}]}'), model="m") is None


def test_server_check_reports_unreachable_and_missing_model():
    assert checked(Refused()) == "unreachable"
    assert checked(Tags(b'{"models":[{"name":"other:1b"}]}')) == "model_missing"


def test_server_check_does_not_warn_about_unexpected_answers():
    assert checked(Tags(b"not json")) is None
    assert checked(Tags(b'{"models":"x"}')) is None


@pytest.mark.parametrize(
    "problem, expected",
    [("unreachable", "--ollama-url"), ("model_missing", "ollama pull qwen2.5:3b")],
)
def test_startup_warning_names_the_address_and_fix(problem, expected):
    class Provider:
        model = "qwen2.5:3b"

        def check_server(self):
            return problem

    text = startup_warning(Provider(), "http://localhost:11434")
    assert expected in text
    assert problem != "unreachable" or "http://localhost:11434" in text


def test_no_startup_warning_when_server_is_ready_or_in_demo_mode():
    class Provider:
        def check_server(self):
            return None

    assert startup_warning(Provider(), "x") is None
    assert startup_warning(DemoProvider(), "x") is None
