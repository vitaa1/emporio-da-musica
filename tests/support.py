"""Shared synthetic provider and conversation builders for offline tests."""

import json


class FakeProvider:
    def __init__(self):
        self.responses = []
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response)


def turn(app, *intents):
    app.provider.responses.append({"intents": intents})
    return app.handle("synthetic customer message")


def update(app, **fields):
    pending = app.session.pending[0]
    app.provider.responses.append(
        {
            "pending_id": pending.pending_id,
            "update": {"type": pending.declarations.intent.type, **fields},
        }
    )
    return app.handle("synthetic correction")


def search(query):
    return {"type": "product_search", "query": query}


def payment(**fields):
    return {"type": "payment_options", **fields}
