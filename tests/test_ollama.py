"""Offline transport contract checks; no running Ollama or credentials required."""

import json
from io import BytesIO
from urllib.error import URLError

import pytest

from emporio_da_musica.providers.base import ProviderError, ProviderRequest
from emporio_da_musica.providers.ollama import OllamaProvider


class Transport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return BytesIO(self.response)


def test_request_uses_schema_and_nonstreaming_response():
    provider = OllamaProvider()
    content = '{"intents":[{"type":"product_search","query":"Yamaha"}]}'
    provider.opener = Transport(
        json.dumps({"done": True, "message": {"content": content}}).encode()
    )
    assert provider.propose(ProviderRequest(message="Quero Yamaha")) == content
    request, timeout = provider.opener.calls[0]
    body = json.loads(request.data)
    assert body["format"]["$defs"]["ProductSearch"]["additionalProperties"] is False
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert timeout == 120


@pytest.mark.parametrize(
    "response",
    [
        b"invalid",
        b"[" * 20000 + b"]" * 20000,
        b"{}",
        b"[]",
        b"x" * 256001,
        b'{"done":false,"message":{"content":"{}"}}',
        b'{"done":true,"done_reason":"length","message":{"content":"{}"}}',
        b'{"done":true,"message":{"content":null}}',
        URLError("sensitive error"),
        TimeoutError("sensitive error"),
    ],
)
def test_invalid_responses_are_redacted_and_not_retried(response):
    provider = OllamaProvider()
    provider.opener = Transport(response)
    with pytest.raises(ProviderError, match="^Ollama request failed$"):
        provider.propose(ProviderRequest(message="test"))
    assert len(provider.opener.calls) == 1


@pytest.mark.parametrize(
    "url",
    ["file:///tmp/test", "http://user:pass@localhost", "http://localhost?token=secret"],
)
def test_invalid_configuration(url):
    with pytest.raises(ValueError):
        OllamaProvider(base_url=url)


def test_current_message_follows_history_and_no_pending_disallows_updates():
    from emporio_da_musica.contracts.session import ConversationMessage

    provider = OllamaProvider()
    provider.opener = Transport(b'{"done":true,"message":{"content":"{}"}}')
    provider.propose(
        ProviderRequest(
            message="uma unidade",
            history=(ConversationMessage(role="user", content="older query"),),
        )
    )
    body = json.loads(provider.opener.calls[0][0].data)
    assert body["messages"][-1]["content"].endswith("uma unidade")
    assert "pending_id" not in body["format"].get("properties", {})
    assert "intents" in body["format"]["properties"]
    assert "Versão 2.1" in body["messages"][0]["content"]


def test_ordinal_schema_tracks_current_display_without_mutating_other_requests():
    from emporio_da_musica.providers.base import PendingHint

    provider = OllamaProvider()
    provider.opener = Transport(b'{"done":true,"message":{"content":"{}"}}')
    pending = (
        PendingHint(
            pending_id="test",
            operation="payment_options",
            requested_fields=("product_reference",),
        ),
    )
    for names, expected in [
        (("First", "Second"), [1, 2]),
        (("Second",), [1]),
        ((), None),
    ]:
        provider.propose(
            ProviderRequest(
                message="two units", pending=pending, displayed_product_names=names
            )
        )
        body = json.loads(provider.opener.calls[-1][0].data)
        ordinal = body["format"]["$defs"]["OrdinalReference"]["properties"]["ordinal"]
        assert ordinal.get("enum") == expected


def test_interrupted_http_body_is_redacted_without_retry():
    from http.client import HTTPResponse

    class Socket:
        def makefile(self, mode):
            return BytesIO(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"20\r\nsensitive partial body"
            )

    class InterruptedTransport:
        calls = 0

        def open(self, request, timeout):
            self.calls += 1
            response = HTTPResponse(Socket())
            response.begin()
            return response

    provider = OllamaProvider()
    provider.opener = InterruptedTransport()
    with pytest.raises(ProviderError, match="^Ollama request failed$"):
        provider.propose(ProviderRequest(message="synthetic query"))
    assert provider.opener.calls == 1
