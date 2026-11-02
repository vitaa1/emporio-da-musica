# Empório da Música

## Architecture planning

The application is currently in planning; only the development environment is implemented. The planned solution is a Python CLI with LLM intent extraction, a Python controller, in-memory CSV queries, deterministic business rules, and direct composition of critical results.

- [Architecture, scope, and policy decisions](docs/ARCHITECTURE.md)
- [Agent–controller contract](docs/CONTRACT.md)
- [GitHub milestones and ready-to-copy issues](docs/GITHUB_PLAN.md)
- [Project handoff and source analysis](CONTEXT.md)

These documents describe planned behavior, not available application commands. Detailed contract defaults remain proposals. Architecture now records P03 policy decisions and explicit deferrals; these were checked against the supplied manual, but runtime rules are not implemented yet.

## Prototype policy assumptions

The challenge permits reasonable documented interpretations. For implementation, prefer the detailed installment bands over the payment summary; defer the ambiguous 2–3 installment band and combined-payment calculations for confirmation. Initially support local freight only for a declared Campo Grande/MS destination, using item totals after applicable discounts and before freight; exactly BRL 500 requires confirmation. Other metropolitan destinations, the preference-exchange starting event, and conflicting contact details also require confirmation. These decisions and their source references are detailed in [architecture](docs/ARCHITECTURE.md#policy-decisions-for-implementation-p03--issue-4).

Order access will use an explicitly simulated identity fixed outside model output. Date calculations will use an injected clock in `America/Campo_Grande`, with the starting date as day zero and the final calendar day included. Missing holiday data prevents exact business-day deadlines. These are prototype boundaries, not implemented features, production authentication, or authorization to perform refunds or other transactions.

## Development environment

Use Python 3.13 with a project-local virtual environment. Development and dependency generation use Linux/WSL (Ubuntu); CI also checks installation on Windows and macOS. Keep Windows and Linux environments separate.

### Install Python and dependencies

If Python 3.13 is unavailable, install it with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
sh /tmp/uv-install.sh
~/.local/bin/uv python install 3.13
~/.local/bin/python3.13 --version
```

From the repository root, create `.venv` only if it does not exist, then install the pinned dependencies:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

If the interpreter is not on PATH, use `~/.local/bin/python3.13`. Activation is optional: use explicit `.venv/bin/python` paths. On Windows, create a separate environment with `py -3.13 -m venv .venv` and use `.\.venv\Scripts\python.exe` for subsequent commands.

### Verify the environment

```sh
.venv/bin/python --version
.venv/bin/python -m pip --version
.venv/bin/python -m pip check
.venv/bin/python -m piptools compile --version
.venv/bin/python -m ruff --version
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Python must be 3.13.x and pip must belong to the project environment. There is no application or test suite yet; Ruff may report that no Python files exist. These commands validate tooling, not application behavior.

### Style and formatting

`.editorconfig` defines UTF-8, LF endings, a final newline, four-space indentation, and two spaces for YAML/JSON. Markdown preserves trailing spaces used for line breaks. Use an editor with EditorConfig support; no editor-specific configuration is required.

Ruff configuration lives in `pyproject.toml`: Python 3.13, 88-column formatting, double quotes, basic error checks (`E4`, `E7`, `E9`, `F`), and import sorting (`I`). Local agent tooling and environment backups are excluded. See the [Ruff configuration reference](https://docs.astral.sh/ruff/configuration/).

To apply formatting and safe lint fixes, then review the diff:

```sh
.venv/bin/python -m ruff check --fix .
.venv/bin/python -m ruff format .
```

### Optional VS Code workflow

Open the repository from a WSL terminal with `code .` when VS Code's [WSL support](https://code.visualstudio.com/docs/remote/wsl) is installed. Confirm the window is connected to WSL, then use **Python: Select Interpreter** to choose the project's `.venv/bin/python`; see [Python environments](https://code.visualstudio.com/docs/python/environments). Do not select a Windows interpreter for this checkout.

EditorConfig support and the Ruff extension are optional conveniences. The terminal commands above remain the source of truth. No `.vscode` files or machine-specific interpreter paths are required or committed.

### Generate dependencies

`pyproject.toml` declares direct dependencies; `requirements-dev.txt` pins development dependencies and their transitive dependencies. Runtime dependencies are empty. Introduce `requirements.txt` with the first runtime dependency.

Linux/WSL with Python 3.13 is now the generation reference, replacing Windows to match the development environment. The Linux CI job regenerates the file and checks for differences; all three platforms still install it and run setup checks. `colorama` is explicitly declared to retain the existing Windows dependency of `build` in this shared file. Review platform-specific dependencies whenever adding tools; a Linux-generated file alone does not guarantee compatibility elsewhere.

Generate in the reference environment using the installed pinned pip-tools, without manually editing the output:

```sh
CUSTOM_COMPILE_COMMAND='pip-compile --allow-unsafe --extra=dev --output-file=requirements-dev.txt --strip-extras pyproject.toml' .venv/bin/python -m piptools compile --extra=dev --allow-unsafe --strip-extras --output-file=requirements-dev.txt pyproject.toml
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
```

Review and commit declarations and generated pins together. Do not use `--upgrade` unless deliberately updating existing dependencies. Windows/macOS contributors should use Linux/WSL for generation.

### Recreate the environment

Stop processes using `.venv` and deactivate it if active. On Linux/WSL, rename it to an unused backup name:

```sh
mv -T -n .venv .venv-backup
```

Confirm `.venv` no longer exists before creating and installing again. Remove the backup after validating the new environment. Never commit environments or backups.

### Continuous integration

Pull requests targeting `main` and pushes to `main` run `setup-python-windows`, `setup-python-linux`, and `setup-python-macos`. Each creates a fresh Python 3.13 environment, installs the pins, runs `pip check`, verifies pip-tools, and checks Ruff lint and formatting. Only Linux regenerates dependencies and compares the result with the committed file.

Keep all three checks required before merge. No provider credentials are needed. New workflow changes still require a remote CI run before their cross-platform results can be claimed.

### Local configuration

Virtual environments, backups, Python/Ruff caches, and `.env` files are ignored. Commit `.env.example` only with nonsecret example values.

## Contributor workflow

Create a dedicated issue branch before changing files; never develop directly on `main`. Keep each PR focused, link its issue, and describe the change, verification, and remaining limitations. Use `docs:`, `chore:`, or `ci:` commit prefixes as appropriate. Review generated pins together with their declarations and require all three CI checks before merge.

See [AGENTS.md](AGENTS.md) for repository conventions. Development skills under `.agents/skills/` and `skills-lock.json` are versioned for a shared workflow. They are optional for running the application; see their [source and license](.agents/skills/README.md). The optional [development reviewers](.codex/agents/README.md) are versioned with the repository.

## Setup verification

On 2026-11-02, setup was verified on Ubuntu 24.04.1 under WSL2 with Python 3.13.18. A clean export of commit `74eb53c` was placed in a temporary directory, a new `.venv` was created, and `requirements-dev.txt` was installed without reusing the project's environment.

The commands under **Verify the environment** passed: pip 26.2.2 belonged to the temporary environment, `pip check` reported no broken requirements, pip-tools was 7.6.2, and Ruff was 0.17.3. Regenerating the pins produced a byte-identical file. Ruff found no lint violations; formatting reported one file already formatted. There is no application Python code yet.

The [CI run for the merged tooling change](https://github.com/vitaa1/emporio-da-musica/actions/runs/41445792754) passed all three platform checks. Windows/macOS verification used hosted runners, not local manual execution. Interpreter installation from scratch, VS Code integration, and application behavior were not tested in this validation. Setup requires an available Python 3.13 interpreter and access to the package index (or suitable cached packages); no LLM credentials are required.
