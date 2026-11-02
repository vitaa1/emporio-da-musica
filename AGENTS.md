# Repository Guidelines

## Project Structure & Documentation

The repository contains Python environment scaffolding and planning documents; application code and tests are not implemented yet.

- `pyproject.toml`: Python `>=3.13,<3.14`, metadata, and direct dependencies.
- `requirements-dev.txt`: generated dependency pins.
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
```

Create `.venv` only when absent. Follow README instructions for pip-tools generation in the Linux/WSL reference environment. Never edit generated pins manually; keep them with declaration changes. Introduce `requirements.txt` with the first runtime dependency.

## Style & Validation

Use four-space Python indentation, two-space YAML indentation, `snake_case` functions/modules, and `PascalCase` classes. Write documentation, comments, and commits in English; discuss work in Portuguese.

EditorConfig and Ruff are configured; Ruff checks basic errors and import order and formats Python at 88 columns. Pytest is planned, not installed. Use pytest for rules/controller tests and separate evaluations for model interpretation and grounding. Keep deterministic CI credential-free. Test boundaries, missing facts, authorization, and failures. Current CI checks setup, lint, and formatting on Windows, Linux, and macOS; only Linux regenerates dependency pins; no application test command exists yet.

## Contributions & Local Configuration

Use `docs:`, `chore:`, or `ci:` where appropriate. Create a focused issue branch before any new feature or task; never develop directly on main. Use PRs; describe behavior, verification, and limitations. Require all three `setup-python-*` checks before merge. Branch creation for new work is authorized by the user. Obtain explicit authorization before installing tools or performing other Git mutations.

Keep secrets, environments, backups, and unnecessary customer data out of commits/logs. Commit only nonsecret `.env.example` values. Keep Windows and Linux environments separate.
