"""Shared synthetic provider and conversation builders for offline tests."""

import json


class FakeProvider:
    def __init__(self):
        self.responses = []
        self.requests = []
        self.policy_responses = []
        self.policy_requests = []

    def explain(self, request):
        self.policy_requests.append(request)
        response = self.policy_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response)

    def propose(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response)


METHOD_WORDS = {
    "pix": "pix",
    "debit": "debito",
    "credit": "credito",
    "boleto": "boleto",
    "combined": "pagamento combinado",
}


def _message(base, *intents):
    """A neutral message naming only the payment methods the intents declare."""
    methods = [i.get("payment_method") for i in intents]
    return " ".join([base, *(METHOD_WORDS[m] for m in methods if m)])


def turn(app, *intents, message=None):
    app.provider.responses.append({"intents": intents})
    if message is None:
        message = _message("synthetic customer message", *intents)
    return app.handle(message)


def update(app, message=None, **fields):
    pending = app.session.pending[0]
    if message is None:
        message = _message("synthetic correction", fields)
    app.provider.responses.append(
        {
            "pending_id": pending.pending_id,
            "update": {"type": pending.declarations.intent.type, **fields},
        }
    )
    return app.handle(message)


def search(query):
    return {"type": "product_search", "query": query}


def payment(**fields):
    return {"type": "payment_options", **fields}
