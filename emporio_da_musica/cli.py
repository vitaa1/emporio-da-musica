"""Offline catalog CLI with an explicitly limited demonstration provider."""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .contracts.common import MAX_MESSAGE_LENGTH
from .controller import Controller
from .data.loader import DataError, load_snapshot
from .providers.demo import DemoProvider
from .providers.ollama import OllamaProvider

HELP = """Demonstração offline, sem modelo de linguagem.
/buscar NOME — procurar produtos (ou /buscar para listar)
/preco POSICAO QUANTIDADE FORMA — consultar preço; formas: pix, debit, credit, boleto
/escolher POSICAO — responder à seleção pendente
/quantidade NUMERO — responder à quantidade pendente
/pagamento FORMA — responder à forma de pagamento pendente
/pedido [NUMERO] — consultar pedido do cliente simulado (requer --customer-id)
/cancelar — cancelar consultas pendentes
/sair — encerrar
"""


COMMAND_USAGE = {
    "/preco": "Use /preco POSICAO QUANTIDADE FORMA. Exemplo: /preco 1 1 pix.",
    "/escolher": "Use /escolher POSICAO. Exemplo: /escolher 1.",
    "/quantidade": "Use /quantidade NUMERO. Exemplo: /quantidade 1.",
    "/pagamento": "Use /pagamento FORMA. Exemplo: /pagamento pix.",
    "/pedido": "Use /pedido NUMERO. Exemplo: /pedido 4.",
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
    if command == "/pedido":
        if len(args) > 1 or not all(
            value.isascii() and value.isdecimal() and int(value) > 0 for value in args
        ):
            return COMMAND_USAGE[command]
    elif command in COMMAND_USAGE:
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
    help_text = (
        HELP
        if isinstance(controller.provider, DemoProvider)
        else "Olá! Sou o assistente do Empório da Música. Conte o que você procura. Use /sair para encerrar e /cancelar para cancelar consultas pendentes.\n"
    )
    destination.write(help_text)
    customer_id = controller.session.simulated_customer_id
    if customer_id is not None:
        destination.write(
            f"Sessão de demonstração do cliente simulado {customer_id}; "
            "isto não é autenticação real.\n"
        )
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
                destination.write(help_text)
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
        default=False,
        help="Use the offline command-based fake provider",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data/demo",
    )
    parser.add_argument(
        "--ollama-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--manual", type=Path, help="Reviewed UTF-8 manual text")
    parser.add_argument(
        "--customer-id",
        type=int,
        help="Simulated customer for order lookup (demonstration, not authentication)",
    )
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.data_dir)
    except DataError as error:
        parser.exit(1, f"Data validation failed: {error}\n")
    try:
        manual = args.manual.read_text(encoding="utf-8") if args.manual else None
        provider = (
            DemoProvider()
            if args.demo
            else OllamaProvider(
                base_url=args.ollama_url,
                model=args.model,
                timeout=args.timeout,
                manual=manual,
            )
        )
    except (ValueError, OSError):
        parser.exit(1, "Invalid provider configuration or unreadable manual.\n")
    try:
        controller = Controller(
            snapshot,
            provider,
            clock=lambda: datetime.now(timezone.utc),
            customer_id=args.customer_id,
        )
    except ValueError:
        parser.exit(1, "Unknown simulated customer.\n")
    run_cli(controller, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
