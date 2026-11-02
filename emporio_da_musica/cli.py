"""Offline catalog CLI with an explicitly limited demonstration provider."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .contracts.common import MAX_MESSAGE_LENGTH
from .controller import Controller
from .data import DataError, load_snapshot
from .provider import ProviderError

HELP = """Demonstração offline, sem modelo de linguagem.
/buscar NOME — procurar produtos (ou /buscar para listar)
/preco POSICAO QUANTIDADE FORMA — consultar preço; formas: pix, debit, credit, boleto
/escolher POSICAO — responder à seleção pendente
/quantidade NUMERO — responder à quantidade pendente
/pagamento FORMA — responder à forma de pagamento pendente
/cancelar — cancelar consultas pendentes
/sair — encerrar
"""


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


COMMAND_USAGE = {
    "/preco": "Use /preco POSICAO QUANTIDADE FORMA. Exemplo: /preco 1 1 pix.",
    "/escolher": "Use /escolher POSICAO. Exemplo: /escolher 1.",
    "/quantidade": "Use /quantidade NUMERO. Exemplo: /quantidade 1.",
    "/pagamento": "Use /pagamento FORMA. Exemplo: /pagamento pix.",
}
UPDATE_FIELDS = {
    "/escolher": "product_reference",
    "/quantidade": "quantity",
    "/pagamento": "payment_method",
}


def demo_guidance(message, session):
    """Reject command usage mistakes locally, without model repair or error logs."""
    parts = message.split()
    if not parts:
        return "Digite /buscar NOME para começar ou /ajuda para ver os comandos."
    command, args = parts[0], parts[1:]
    if command in COMMAND_USAGE:
        expected = 3 if command == "/preco" else 1
        valid = len(args) == expected
        if valid and command in {"/preco", "/escolher", "/quantidade"}:
            numbers = args[:2] if command == "/preco" else args
            valid = all(
                value.isascii() and value.isdecimal() and int(value) > 0
                for value in numbers
            )
        if valid and command in {"/preco", "/pagamento"}:
            valid = args[-1] in {"pix", "debit", "credit", "boleto", "combined"}
        if not valid:
            return COMMAND_USAGE[command]
        if command in UPDATE_FIELDS:
            if not session.pending:
                return "Não há consulta pendente. Use /buscar NOME e depois /preco 1 1 pix."
            if UPDATE_FIELDS[command] not in session.pending[0].requested_fields:
                return "Esse dado não foi solicitado na consulta pendente. Responda ao que foi pedido ou use /cancelar."
    elif command not in {"/buscar", "/cancelar"}:
        return "Comando não reconhecido. Use /ajuda para ver exemplos."
    elif command == "/cancelar" and args:
        return "Use /cancelar sem argumentos para cancelar as consultas pendentes."
    return None


def run_cli(controller, source, destination):
    destination.write(HELP)
    try:
        while True:
            destination.write("> ")
            destination.flush()
            line = source.readline(MAX_MESSAGE_LENGTH + 2)
            if not line:
                break
            if len(line.rstrip("\r\n")) > MAX_MESSAGE_LENGTH:
                while line and not line.endswith("\n"):
                    line = source.readline(MAX_MESSAGE_LENGTH + 2)
                destination.write("Mensagem muito longa; limite de 4.000 caracteres.\n")
                continue
            message = line.strip()
            if message == "/sair":
                break
            if message == "/ajuda":
                destination.write(HELP)
                continue
            if isinstance(controller.provider, DemoProvider):
                guidance = demo_guidance(message, controller.session)
                if guidance:
                    destination.write(guidance + "\n")
                    continue
            destination.write(controller.handle(message).text + "\n")
    except (KeyboardInterrupt, EOFError):
        pass
    destination.write("Até mais!\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo",
        action="store_true",
        required=True,
        help="Use the offline command-based fake provider",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data/demo",
    )
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.data_dir)
    except DataError as error:
        parser.exit(1, f"Data validation failed: {error}\n")
    controller = Controller(
        snapshot, DemoProvider(), clock=lambda: datetime.now(timezone.utc)
    )
    run_cli(controller, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
