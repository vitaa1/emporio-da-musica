# Agent evaluations

The deterministic suite runs in CI without Ollama or credentials:

```sh
.venv/bin/python -m pytest -q
```

The existing `python -m evals.ollama` command remains the three-turn development
smoke test. The broader suite is explicitly opt-in and uses only `data/demo/`:

```sh
.venv/bin/python -m evals.suite --url http://localhost:11434 --output /tmp/emporio-evaluation.json
```

Use the Windows host URL when Ollama runs outside WSL. The server must already
have `qwen2.5:3b`, or pass `--model MODEL` for an installed model. No downloads or
server startup are performed. Each scenario starts a new controller session;
turns within it run sequentially, including turns after a failed assertion.
The clock is fixed at the run's starting instant. Customer 3 is a simulated
identity, never an identity established by a chat message.

`scenarios.json` versions the inputs and expected outcomes. Required results
must match exactly in count, while explicitly listed optional results may occur
once each. Dictionaries match specified fields; lists match length and position;
BRL amounts compare numerically. This permits a catalog listing alongside a
clarification only when it names the expected product. Unexpected operations,
wrong quantities/products/amounts, and empty result sets fail. Overlapping
expectations are matched one-to-one without depending on result order. These checks assess
end-to-end interpretation and execution, not isolated raw extraction accuracy.
They do not assert that every unchecked field or sentence is correct.

The report records actual customer messages, rendered responses, structured
results, verdicts, per-turn wall time, configuration, and SHA-256 hashes of the
cases, evaluator, application Python sources, prompts, manual, and demo CSVs. Token usage is unavailable through the
current adapter. Cold loading, caching, and extraction retries can affect latency;
these runs are not controlled performance benchmarks. Reports contain only the
synthetic demonstration conversation; do not use this runner with private data.
Existing output paths are rejected to preserve evidence. Completed scenarios are
saved incrementally; interrupted reports retain `complete: false` and may omit
the interrupted scenario. Exit code 1 means an automated assertion failed;
exit code 0 does not mean manual grounding review passed.

For a targeted diagnostic, repeat `--scenario ID` as needed:

```sh
.venv/bin/python -m evals.suite --scenario promotion-injection --output /tmp/emporio-promotion.json
```

Policy prose requires manual comparison with the referenced manual sections.
`manual_status: pending` is deliberately emitted even on automated success.
Record review findings separately, retaining the original report. Check every
factual claim, policy citation, omissions material to the question, and any
claim that a purchase, refund, complaint, or transfer occurred. For mixed
questions, check that all independent questions were answered. For clarification
flows, check that unknown facts remain unknown.

This set includes new wording and adversarial cases as well as known development
regressions; it is separate from the prompt files but is not an independent
held-out benchmark. The `origin` field identifies that overlap. Do not derive a
general reliability percentage from this small, development-informed sample.
Observed failures can be documented rather than silently changing expected
behavior to fit the model. See the [evaluation report](../docs/EVALUATION.md).

## Deterministic coverage retained in CI

| Concern | Existing evidence |
| --- | --- |
| Promotion/PIX precedence, rounding, installments | `tests/test_catalog.py`: `test_discount_precedence`, installment boundary and rounding tests |
| Customer authorization and nonrevealing failures | `tests/test_orders.py`: foreign/nonexistent equivalence, absent identity, identity excluded from provider requests |
| Receipt provenance and date boundaries | `tests/test_returns.py`: invented receipt discarded, delivery estimate never substitutes for receipt, seven-day boundary |
| References, missing facts, multi-intent dependencies | `tests/test_controller.py`: ordinal resolution, scoped clarification, independent operations, stale-selection clearing |
| Invalid extraction and provider/operation failure | `tests/test_contracts.py`, `tests/test_controller.py`, `tests/test_ollama.py`: schema injection, repair limits, truncated bodies, sanitized failures |
| Policy grounding guards and false executed actions | `tests/test_policy.py`: invalid numbers/sections, invented contacts, executed-action prose rejected |
| Scope and complaints | `tests/test_policy.py`, `tests/test_composer.py`: accessory distinctions and fixed complaint response |
| Evaluation false positives/negatives | `tests/test_evaluation.py`: wrong product/quantity/amount, missing/extra results, optional catalogs, continued evaluation and manual-review state |

These offline tests use controlled proposals and test Python guarantees. They do
not measure the model's natural-language interpretation. The existing three
`setup-python-*` CI jobs already run all these tests and Ruff; no workflow change
or live-model dependency is necessary.
