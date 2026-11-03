"""Opt-in end-to-end model evaluation; deterministic checks do not prove grounding."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from emporio_da_musica.controller import Controller
from emporio_da_musica.data.loader import load_snapshot
from emporio_da_musica.providers.ollama import OllamaProvider

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).with_name("scenarios.json")


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    expected: list[dict] = Field(min_length=1)
    optional_results: list[dict] = Field(default_factory=list)
    manual_review: str | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    customer_id: int | None
    origin: str
    turns: list[Step] = Field(min_length=1)


def load_cases():
    cases = TypeAdapter(list[Scenario]).validate_json(CASES.read_text(encoding="utf-8"))
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate scenario IDs")
    for case in cases:
        for step in case.turns:
            for expected in step.expected:
                if not {"operation", "status"} <= expected.keys():
                    raise ValueError("Every expectation needs operation and status")
    return cases


def matches(actual, expected, key=""):
    """Match declared fields, normalizing only BRL amounts, never missing values."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(actual[k], value, k)
            for k, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(matches(a, e) for a, e in zip(actual, expected))
        )
    if key.endswith("_brl") and actual is not None:
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except InvalidOperation:
            return False
    return actual == expected


def check_results(actual, expected, optional=()):
    """Require exactly the expected operations, independent of display ordering."""
    # A broad expectation must not consume the only match for a specific one.
    # There are at most five requested intents, so a small exhaustive assignment
    # is clearer than an ordering heuristic that can silently misgrade a run.
    requirements = [(item, False) for item in expected] + [
        (item, True) for item in optional
    ]

    def assign(remaining, index):
        if index == len(requirements):
            return not remaining
        item, may_skip = requirements[index]
        for i, value in enumerate(remaining):
            if matches(value, item) and assign(
                remaining[:i] + remaining[i + 1 :], index + 1
            ):
                return True
        return may_skip and assign(remaining, index + 1)

    if assign(list(actual), 0):
        return []
    return [{"expected": expected, "optional_results": optional, "actual": actual}]


def run_scenario(case, controller, *, progress=None):
    turns = []
    for number, step in enumerate(case.turns, 1):
        start = time.monotonic()
        response = controller.handle(step.message)
        results = [
            r.model_dump(mode="json", exclude={"result_id"}) for r in response.results
        ]
        failures = check_results(results, step.expected, step.optional_results)
        turn = {
            "turn": number,
            "message": step.message,
            "response": response.text,
            "results": results,
            "expected": step.expected,
            "optional_results": step.optional_results,
            "automated_pass": not failures,
            "failures": failures,
            "seconds": round(time.monotonic() - start, 3),
            "manual_review": step.manual_review,
            "manual_status": "pending" if step.manual_review else "not_requested",
        }
        turns.append(turn)
        if progress:
            progress(case.id, turn)
    return {
        "id": case.id,
        "customer_id": case.customer_id,
        "origin": case.origin,
        "turns": turns,
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--scenario", action="append", help="Run only these scenario IDs"
    )
    args = parser.parse_args()
    cases = load_cases()
    if args.scenario:
        unknown = set(args.scenario) - {case.id for case in cases}
        if unknown:
            parser.error(f"Unknown scenarios: {sorted(unknown)}")
        cases = [case for case in cases if case.id in args.scenario]
    if args.output.exists():
        parser.error(
            "Output already exists; choose a new path to preserve earlier results"
        )
    snapshot = load_snapshot(ROOT / "data/demo")
    provider = OllamaProvider(base_url=args.url, model=args.model)
    started = datetime.now(timezone.utc)
    report = {
        "started_at": started.isoformat(),
        "model": args.model,
        "configuration": {
            "temperature": 0,
            "num_ctx": 16384,
            "num_predict": 2048,
            "timeout_seconds": 120,
        },
        "clock": "Fixed at run start; relative dates use America/Campo_Grande",
        "usage": "Not exposed by the provider adapter",
        "scope": "End-to-end outcomes, not isolated raw extraction accuracy; manual policy review remains required",
        "hashes": {
            str(path.relative_to(ROOT)): digest(path)
            for path in [
                CASES,
                Path(__file__).resolve(),
                *sorted((ROOT / "emporio_da_musica").rglob("*.py")),
                ROOT / "emporio_da_musica/providers/prompts/extraction.md",
                ROOT / "emporio_da_musica/providers/prompts/policy.md",
                ROOT / "emporio_da_musica/providers/store_manual.txt",
                *sorted((ROOT / "data/demo").glob("*.csv")),
            ]
        },
        "scenarios": [],
        "complete": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def progress(case_id, turn):
        print(
            json.dumps(
                {
                    "scenario": case_id,
                    "turn": turn["turn"],
                    "automated_pass": turn["automated_pass"],
                    "seconds": turn["seconds"],
                }
            ),
            flush=True,
        )

    save()
    for case in cases:
        controller = Controller(
            snapshot, provider, customer_id=case.customer_id, clock=lambda: started
        )
        report["scenarios"].append(run_scenario(case, controller, progress=progress))
        save()
    report["complete"] = True
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    raise SystemExit(
        0
        if all(t["automated_pass"] for s in report["scenarios"] for t in s["turns"])
        else 1
    )


if __name__ == "__main__":
    main()
