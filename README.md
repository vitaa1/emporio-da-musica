# Empório da Música

## Architecture planning

The development environment, in-memory CSV loader, typed agent/controller contracts, catalog search/pricing, and an offline catalog controller/CLI are implemented. Real-model conversation remains planned. The planned solution is a Python CLI with LLM intent extraction, a Python controller, in-memory CSV queries, deterministic business rules, and direct composition of critical results.

- [Architecture, scope, and policy decisions](docs/ARCHITECTURE.md)
- [Agent–controller contract](docs/CONTRACT.md)
- [GitHub milestones and ready-to-copy issues](docs/GITHUB_PLAN.md)
- [Project handoff and source analysis](CONTEXT.md)

These documents distinguish implemented data loading from planned conversational behavior. Contract schemas, limits, and offline catalog execution are implemented; real-model interpretation remains planned. Architecture now records P03 policy decisions and explicit deferrals; these were checked against the supplied manual, with catalog availability and nonstacking price rules now implemented.

## Validate the supplied data (P04)

After installing the development environment, run from the repository root:

```sh
.venv/bin/python -m emporio_da_musica
```

The default is the bundled [demonstration snapshot](data/demo/README.md). No original download is needed. It preserves catalog and order scenarios from the challenge while replacing customer names, phones, emails, cities, order notes, and tracking codes with synthetic values. The linked document describes the exact transformations and limitations. This command validates data and prints counts; the separate offline CLI is described below.

To validate the original six CSVs instead, supply their directory:

```sh
.venv/bin/python -m emporio_da_musica /path/to/challenge/data
```

On Windows, use `.\.venv\Scripts\python.exe`. On WSL, a Windows directory is accessible under `/mnt/c/`; quote paths containing spaces. Original files can stay outside the repository or in ignored `data/source/`. Only `data/demo/` is intended for version control. The loader does not modify either dataset. The PDF is not needed by this command.

Required filenames are `desafio_tecnico_ai_eng - categories.csv`, `desafio_tecnico_ai_eng - products.csv`, `desafio_tecnico_ai_eng - customers.csv`, `desafio_tecnico_ai_eng - orders.csv`, `desafio_tecnico_ai_eng - order_items.csv`, and `desafio_tecnico_ai_eng - promotions.csv`. All must have their supplied header and UTF-8 encoding (an optional BOM is accepted). Column order may vary; missing, duplicate, or additional columns are rejected. Surrounding field whitespace is removed; blank required values and malformed records fail the whole load.

The command prints only table counts on success and exits with status 1 on data errors. The supplied snapshot produces 9 categories, 65 products, 50 customers, 20 orders, 22 order items, and 25 promotions. Counts are audit evidence, not hardcoded validation constraints.

`emporio_da_musica.data.load_snapshot(path)` returns typed records indexed by primary ID (order items by order/product pair), plus products by category, orders by customer, items by order, and promotions by product. IDs and item quantities must be positive integers; stock and amounts may be zero. Amounts use `Decimal`, with at most two decimal places for currency. Percentages are between 0 and 100. Dates must be valid `YYYY-MM-DD` dates. Product specs must be JSON objects; duplicate keys and nonfinite numbers are rejected. Promotion flags accept only `0` and `1`. Only order tracking, estimated delivery, and notes may be blank, becoming `None`.

Known product/order statuses are validated. Historical payment methods preserve `pix`, `debit`, `boleto`, or `credit_1x` through `credit_12x`; loading a recorded payment does not approve current payment conditions. Historical totals are never recomputed. Discontinued/coming-soon stock, empty categories, and inactive promotions remain available as source facts. No stock availability, policy eligibility, or actual receipt is inferred.

The loader validates all foreign keys and duplicate keys before returning a snapshot. Errors identify table, CSV line when available, and field without including source values. Customer and order records are excluded from generated representations. Indexes are internal application data, not an authorization boundary; future order access must enforce the simulated session in Python. The snapshot is mutable in memory and must be treated as read-only by consumers. It is not live inventory or a carrier connection.

## Typed agent/controller contracts

`emporio_da_musica/contracts/` defines strict Pydantic intents, results, clarification updates, and session state. `emporio_da_musica/provider.py` supplies a provider-independent extraction boundary tested with a fake provider. It does not call an LLM or execute business operations yet. See [the contract](docs/CONTRACT.md#implemented-interfaces-and-limits) for payload examples, five-intent limits, missing-quantity behavior, store date handling, and the separation between model proposals and Python-owned identity/prices.

Pydantic validates structure and tzdata supplies the store timezone on all supported platforms. Runtime-only setup uses `.venv/bin/python -m pip install -r requirements.txt`; development setup uses `requirements-dev.txt`, which includes runtime dependencies and pytest/Ruff/pip-tools. No provider credentials are required for the contract tests.

## Catalog search and prices

`emporio_da_musica.catalog.search_catalog(snapshot, ProductSearch(...))` returns a typed result without calling a provider. Search uses case/accent-insensitive substring matching on product names and, separately, category names; repeated whitespace is collapsed and punctuation retained. Both filters must match. No synonyms or fuzzy matching are inferred.

Results are sorted by ascending product ID and limited to five. `CatalogData.total_matches` reports the count before truncation: zero matches return `not_found`, while multiple matches return choices without selecting a product. The future controller must save the actual displayed order for ordinal references. An empty search browses the catalog; empty categories have no results.

Availability requires active status and sufficient stock for the requested quantity. Discontinued and coming-soon statuses override positive stock. Only `available_only=True` filters unavailable products. Missing quantity is treated as a unit-price inquiry with an explicit assumption; this default must not be reused for basket assessments.

Active promotions override the 5% PIX discount (manual §§3, 6), including an active 0% promotion. Inactive promotions are ignored. Multiple active promotions on a matching product require confirmation because precedence is undefined. Prices use Decimal and ROUND_HALF_UP to cents per unit, then multiply by quantity. This rounding convention is a prototype assumption. The budget is inclusive and compares the resulting quantity total, using the requested payment method, before result truncation. Unspecified payment uses list/promotional price with an explicit assumption and no PIX discount.

Combined payment requires confirmation. Installments without a method or with a noncredit method request corrected conditions. Credit requests for 2–3 installments return `requires_confirmation` because the policy is ambiguous. Requests for 4–12 installments return `unavailable` until the payment stage implements the documented bands; no installment eligibility is promised. Quotes for unavailable products are informational snapshot prices, not offers or reservations. The separate offline CLI now exposes catalog execution; live provider integration remains subsequent work.

## Offline catalog conversation (issue #10)

Run the command-based demonstration without credentials:

```sh
.venv/bin/python -m emporio_da_musica.cli --demo
```

Use `--data-dir /path/to/csvs` to select another validated snapshot. The original `python -m emporio_da_musica` count-only validation command is unchanged. Windows uses `.\.venv\Scripts\python.exe`.

Example inputs, executed against the bundled demo during local tests:

```text
/buscar Yamaha
/preco 1 1 pix
/sair
```

`/buscar` with no query lists the first five products. `/preco POSITION QUANTITY METHOD` uses the numbered list from the last response; methods are `pix`, `debit`, `credit`, and `boleto`. `/escolher POSITION`, `/quantidade NUMBER`, and `/pagamento METHOD` answer the first pending clarification when that field was requested. `/cancelar` discards unfinished queries, `/ajuda` shows commands, and `/sair`, EOF, or Ctrl+C ends the session. Commands with missing or invalid arguments show usage examples without invoking extraction. Clarification commands without pending work explain how to start a price query; unrequested fields leave pending work unchanged. The demo provider recognizes these explicit commands only; it is not a language model or a natural-language interpreter.

`Controller(snapshot, provider, clock=...)` accepts any provider implementing the existing extraction protocol. `handle(message)` returns deterministic Portuguese text and typed operation results. It validates the complete proposal before dispatch, permits one schema repair, and executes supported catalog/payment-price requests in source order. Payment requests reuse the catalog's supported price rules, require an explicit quantity/payment method, and do not implement installment eligibility. Other operations report unavailable; order requests without startup identity report unauthorized without querying records. There is no live provider or order lookup in this stage.

Selections resolve in Python: an ordinal refers to the actual list shown before the current turn; `selected` may use a preceding unique successful lookup. Search results and successful product quotes in a response share one numbering sequence in first-display order (at most 25 distinct products). Ambiguous, failed, or unsuccessful reference resolution clears the current selection. Exact resolved IDs are quoted without another name search, including when names are duplicated. Each successful quote participates in the displayed list, preserving its selection when an independent search also runs. A quote-only response lists the quoted products; subsequent ordinals refer to that updated list.

Missing facts create at most five pending operations. A scoped clarification updates and revalidates only its target; resolved product IDs remain pinned while quantity/payment facts are collected. An unresolved product still requires an explicit reference update even if an independent lookup selected another product. Other pending operations remain suspended until their own clarification; no dependency graph or automatic retry is inferred. A new complete intent turn replaces earlier pending work; `/cancelar` explicitly cancels it. Corrections to already completed requests are new turns and recompute prices. The response shows successes first, limitations next, and one focused clarification last.

Input is limited to 4,000 characters; the CLI drains an oversized line without interpreting its remainder. History retains at most 20 messages in memory. Full operational output is displayed, but responses exceeding the history field limit are represented by a fixed summary in history. Provider requests contain the ordered displayed names and pending hints, never customer tables or session identity. Logs include only operation/error class identifiers; expected arithmetic, record-lookup, and validation failures cannot produce fallback prices. Unexpected programming errors are not silently swallowed. Product text is rendered without terminal control characters. No persistent session, paid API, dependency, or transaction capability is added.

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

Python must be 3.13.x and pip must belong to the project environment. The commands above validate tooling and Python style. Data-loader validation is described above.

### Run deterministic tests

```sh
.venv/bin/python -m pytest -q
```

Run from the repository root. Loader tests use small synthetic CSVs in temporary directories; demo tests additionally validate the bundled snapshot and default command. Neither needs the challenge download nor provider credentials. They cover normalization, historical totals, duplicate keys, orphan references, malformed data, optional fields, and the validation command's output and error behavior.

On 2026-11-02, all 192 tests passed locally with Python 3.13.18 and pytest 9.2.0, including loader, bundled demo, contract, 32 catalog tests, and 39 controller/CLI tests. The original six-table snapshot also loaded successfully with the counts listed above. Ruff and `pip check` passed. The updated CI runs these tests on all three platforms; remote results remain pending until this branch is published.

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

`pyproject.toml` declares direct dependencies; `requirements.txt` pins runtime dependencies and `requirements-dev.txt` pins runtime plus development dependencies and their transitive dependencies. Generate both outputs together whenever declarations change.

Linux/WSL with Python 3.13 is now the generation reference, replacing Windows to match the development environment. The Linux CI job regenerates both files and checks for differences; all three platforms still install it and run setup checks. `colorama` is explicitly declared to retain the existing Windows dependency of `build` in this shared file. Review platform-specific dependencies whenever adding tools; a Linux-generated file alone does not guarantee compatibility elsewhere.

Generate in the reference environment using the installed pinned pip-tools, without manually editing the output:

```sh
CUSTOM_COMPILE_COMMAND='pip-compile --allow-unsafe --output-file=requirements.txt --strip-extras pyproject.toml' .venv/bin/python -m piptools compile --allow-unsafe --strip-extras --output-file=requirements.txt pyproject.toml
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

Pull requests targeting `main` and pushes to `main` run `setup-python-windows`, `setup-python-linux`, and `setup-python-macos`. Each creates a fresh Python 3.13 environment, installs the pins, runs `pip check`, verifies pip-tools, checks Ruff lint and formatting, and runs `python -m pytest -q`. Only Linux regenerates dependencies and compares the result with the committed file.

Keep all three checks required before merge. No provider credentials are needed. New workflow changes still require a remote CI run before their cross-platform results can be claimed.

### Local configuration

Virtual environments, backups, Python/Ruff/pytest caches, local source snapshots outside `data/demo/`, and `.env` files are ignored. Commit `.env.example` only with nonsecret example values.

## Contributor workflow

Create a dedicated issue branch before changing files; never develop directly on `main`. Keep each PR focused, link its issue, and describe the change, verification, and remaining limitations. Use `docs:`, `chore:`, or `ci:` commit prefixes as appropriate. Review generated pins together with their declarations and require all three CI checks before merge.

See [AGENTS.md](AGENTS.md) for repository conventions. Development skills under `.agents/skills/` and `skills-lock.json` are versioned for a shared workflow. They are optional for running the application; see their [source and license](.agents/skills/README.md). The optional [development reviewers](.codex/agents/README.md) are versioned with the repository.

## Setup verification

On 2026-11-02, setup was verified on Ubuntu 24.04.1 under WSL2 with Python 3.13.18. A clean export of commit `74eb53c` was placed in a temporary directory, a new `.venv` was created, and `requirements-dev.txt` was installed without reusing the project's environment.

The commands under **Verify the environment** passed: pip 26.2.2 belonged to the temporary environment, `pip check` reported no broken requirements, pip-tools was 7.6.2, and Ruff was 0.17.3. Regenerating the pins produced a byte-identical file. Ruff found no lint violations; formatting reported one file already formatted. At the time of that setup verification, no application Python code existed.

The [CI run for the merged tooling change](https://github.com/vitaa1/emporio-da-musica/actions/runs/41445792754) passed all three platform checks. Windows/macOS verification used hosted runners, not local manual execution. Interpreter installation from scratch, VS Code integration, and application behavior were not tested in this validation. Setup requires an available Python 3.13 interpreter and access to the package index (or suitable cached packages); no LLM credentials are required.
