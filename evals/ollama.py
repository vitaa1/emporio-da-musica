"""Opt-in real-model smoke evaluation using only bundled demonstration data."""

import argparse
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.providers.ollama import OllamaProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--model", default="qwen2.5:3b")
    args = parser.parse_args()
    snapshot = load_snapshot(Path(__file__).resolve().parents[1] / "data/demo")
    controller = Controller(
        snapshot,
        OllamaProvider(base_url=args.url, model=args.model),
        clock=lambda: datetime.now(timezone.utc),
    )
    cases = [
        "Mostre violões Yamaha",
        "Quero 1 unidade do segundo no PIX",
        "Na verdade quero duas unidades no PIX",
    ]
    for index, message in enumerate(cases):
        start = time.monotonic()
        result = controller.handle(message)
        last = result.results[-1] if result.results else None
        passed = bool(
            last
            and last.status == "success"
            and last.operation
            == ("product_search" if index == 0 else "payment_options")
        )
        if passed and index:
            passed = (
                last.data.name == "Yamaha C70 Nylon Natural"
                and last.data.quantity == index
                and last.data.payment_method == "pix"
                and last.data.final_total_brl == Decimal("806.55") * index
            )
        print(
            json.dumps(
                {
                    "case": index + 1,
                    "model": args.model,
                    "passed": passed,
                    "seconds": round(time.monotonic() - start, 2),
                    "status": last.status if last else "invalid_proposal",
                    "operation": last.operation if last else None,
                    "quantity": getattr(last.data, "quantity", None) if last else None,
                    "product": getattr(last.data, "name", None) if last else None,
                }
            )
        )
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
