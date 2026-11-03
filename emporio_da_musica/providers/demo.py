"""Offline command-based provider for the demonstration CLI."""

import json

from .base import ProviderError


class DemoProvider:
    """Command-to-proposal fake; no natural-language interpretation or execution."""

    def propose(self, request):
        parts = request.message.split(maxsplit=1)
        command = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        try:
            if command == "/buscar":
                intent = {"type": "product_search"}
                if rest:
                    intent["query"] = rest
            elif command == "/preco":
                position, quantity, method = rest.split()
                intent = {
                    "type": "payment_options",
                    "product_reference": {"kind": "ordinal", "ordinal": int(position)},
                    "quantity": int(quantity),
                    "payment_method": method,
                }
            elif (
                command == "/pedido"
                and rest
                and request.pending
                and request.pending[0].operation == "order_status"
            ):
                return json.dumps(
                    {
                        "pending_id": request.pending[0].pending_id,
                        "update": {"type": "order_status", "order_id": int(rest)},
                    }
                )
            elif command == "/pedido":
                intent = {"type": "order_status"}
                if rest:
                    intent["order_id"] = int(rest)
            elif (
                command in {"/escolher", "/quantidade", "/pagamento"}
                and request.pending
            ):
                target = request.pending[0]
                if command == "/escolher":
                    patch = {
                        "product_reference": {"kind": "ordinal", "ordinal": int(rest)}
                    }
                elif command == "/quantidade":
                    patch = {"quantity": int(rest)}
                else:
                    patch = {"payment_method": rest}
                return json.dumps(
                    {
                        "pending_id": target.pending_id,
                        "update": {"type": target.operation, **patch},
                    }
                )
            else:
                raise ValueError
        except ValueError:
            raise ProviderError("Invalid demonstration command") from None
        return json.dumps({"intents": [intent]})
