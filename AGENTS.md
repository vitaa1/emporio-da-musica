# Repository Guidelines

## Project Structure & Documentation

The repository contains development tooling, an in-memory CSV loader, typed Pydantic contracts, an offline catalog controller/CLI, and deterministic tests. Live model integration remains planned.

- `emporio_da_musica/`: CSV records, validation, indexes, and a count-only validation command.
- `emporio_da_musica/contracts/`: intents, results, dates, and internal session contracts.
- `emporio_da_musica/data/`: snapshot records and CSV loading in separate modules.
- `emporio_da_musica/providers/`: provider protocol, extraction validation, and demonstration adapter.
- `emporio_da_musica/controller.py`, `composer.py`, and `cli.py`: offline catalog execution, response templates, and demonstration CLI.
- `tests/`: synthetic loader, bundled demo, contract, catalog, and controller/CLI tests.
- `pyproject.toml`: Python `>=3.13,<3.14`, metadata, and direct dependencies.
- `requirements.txt` and `requirements-dev.txt`: generated runtime and development pins.
- `.github/workflows/ci.yml`: cross-platform setup checks.
- `README.md`: setup; `CONTEXT.md`: historical context and current handoff. Verify snapshots against actual files.

Before implementing, read [architecture](docs/ARCHITECTURE.md) and [contracts](docs/CONTRACT.md). Consult [milestones and issues](docs/GITHUB_PLAN.md) for scope and dependencies. Distinguish approved directions from proposed defaults and unresolved policies. Update documentation when behavior changes; do not duplicate detailed contracts here.

## Architecture & Implementation Boundaries

Use one agent, a CLI, CSVs in memory, session-only history, and sequential operations respecting dependencies. Avoid additional infrastructure without a demonstrated need and an explicit scope decision.

The LLM proposes intents; Python validates inputs, resolves references, authorizes access, and executes queries and business rules. Use Pydantic contracts. Model output must not control customer authorization or authoritative prices.

Keep calculations in Python using decimal arithmetic or integer cents. Compose critical prices, stock, order facts, errors, and clarification questions directly in Python without model rewriting. Reserve LLM prose for general policy explanations. Preserve missing facts and ambiguities; never claim an unexecuted action succeeded.

## Development Commands & Dependencies

Use Python 3.13 and explicit virtual-environment paths:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m piptools compile --version
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest -q
```

Create `.venv` only when absent. Follow README instructions for pip-tools generation in the Linux/WSL reference environment. Never edit generated pins manually; keep them with declaration changes. Regenerate both runtime and development dependency outputs when declarations change.

## Style & Validation

Use four-space Python indentation, two-space YAML indentation, `snake_case` functions/modules, and `PascalCase` classes. Write documentation, comments, and commits in English; discuss work in Portuguese.

EditorConfig and Ruff are configured; Ruff checks basic errors and import order and formats Python at 88 columns. Pytest runs the synthetic loader tests. Use pytest for rules/controller tests and separate evaluations for model interpretation and grounding. Keep deterministic CI credential-free. Test boundaries, missing facts, authorization, and failures. Current CI checks setup, lint, formatting, and deterministic pytest tests on Windows, Linux, and macOS; only Linux regenerates dependency pins.

## Contributions & Local Configuration

Use `docs:`, `chore:`, or `ci:` where appropriate. Create a focused issue branch before any new feature or task; never develop directly on main. Use a descriptive branch name without issue numbers (for example, `feature/csv-loader`). Use descriptive PR titles without planning codes such as P05; describe behavior, verification, and limitations. Require all three `setup-python-*` checks before merge. Branch creation for new work is authorized by the user. Obtain explicit authorization before installing tools or performing other Git mutations.

Keep secrets, environments, backups, and unnecessary customer data out of commits/logs. Commit only nonsecret `.env.example` values. Keep Windows and Linux environments separate.
