# Empório da Música

## Architecture planning

The agent is a Python CLI with local LLM intent extraction (Ollama), a Python controller, in-memory CSV queries, deterministic business rules, and direct composition of critical results. Implemented: catalog search and prices, credit installments, local freight, session-scoped order lookup, return and exchange assessments, general policy answers, and out-of-scope, small-talk, and complaint messages. Live quality findings are documented in `docs/OLLAMA_EVALUATION.md`. Consolidated evaluation, interaction examples, and the final submission README remain (P13, P14).

- [Architecture, scope, and policy decisions](docs/ARCHITECTURE.md)
- [Agent–controller contract](docs/CONTRACT.md)
- [GitHub milestones and ready-to-copy issues](docs/GITHUB_PLAN.md)
- [Project handoff and source analysis](CONTEXT.md)

These documents record the architecture, the P03 policy decisions and explicit deferrals (checked against the supplied manual), the implemented contracts, and the milestone plan. Model interpretation is evaluated separately from deterministic tests.

## Package organization

- `data/records.py`: typed records and the in-memory snapshot, without CSV parsing dependencies.
- `data/loader.py`: CSV parsing, source validation, relationship checks, and index construction.
- `providers/base.py`: provider-neutral request contracts, protocol, and errors.
- `providers/extraction.py`: proposal validation and the single schema-repair attempt.
- `providers/demo.py`: command-based demonstration adapter used for offline runs (`/buscar`, `/preco`, `/pedido`).
- `providers/ollama.py`: local Ollama adapter (P08); see the Ollama section below.
- `contracts/`: typed intents, results, dates, and session state.
- `providers/policy.py` and `providers/prompts/`: policy-answer validation and the versioned extraction and policy prompts.
- `controller.py`, `catalog.py`, `returns.py`, `composer.py`, and `cli.py`: orchestration, catalog/price/installment rules, return assessments, response rendering, and terminal interaction respectively.

Imports target these modules explicitly; package initializers do not eagerly import adapters or loaders. The CLI owns demo usage guidance and constructs the provider. The controller depends on the provider protocol and extraction function. Domain/session code imports snapshot types from `data.records`, without importing the CSV loader.

The package reorganization changes Python import paths: use `data.loader` for `load_snapshot`/`DataError`, `data.records` for record types, and `providers.base`/`providers.extraction` for the former provider module. `DemoProvider` belongs to `providers.demo`. Both documented CLI commands retain their behavior and paths.

Tests separate controller behavior (`test_controller.py`), terminal interaction (`test_cli.py`), rendering (`test_composer.py`), and per-feature rules (`test_catalog.py`, `test_orders.py`, `test_policy.py`, `test_returns.py`, `test_shipping.py`). Shared synthetic setup is in `conftest.py` and conversation builders are in `support.py`. Existing assertions and parameterized cases are preserved; this refactor adds no runtime dependency or application capability.

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

`emporio_da_musica.data.loader.load_snapshot(path)` returns typed records indexed by primary ID (order items by order/product pair), plus products by category, orders by customer, items by order, and promotions by product. IDs and item quantities must be positive integers; stock and amounts may be zero. Amounts use `Decimal`, with at most two decimal places for currency. Percentages are between 0 and 100. Dates must be valid `YYYY-MM-DD` dates. Product specs must be JSON objects; duplicate keys and nonfinite numbers are rejected. Promotion flags accept only `0` and `1`. Only order tracking, estimated delivery, and notes may be blank, becoming `None`.

Known product/order statuses are validated. Historical payment methods preserve `pix`, `debit`, `boleto`, or `credit_1x` through `credit_12x`; loading a recorded payment does not approve current payment conditions. Historical totals are never recomputed. Discontinued/coming-soon stock, empty categories, and inactive promotions remain available as source facts. No stock availability, policy eligibility, or actual receipt is inferred.

The loader validates all foreign keys and duplicate keys before returning a snapshot. Errors identify table, CSV line when available, and field without including source values. Customer and order records are excluded from generated representations. Indexes are internal application data, not an authorization boundary; future order access must enforce the simulated session in Python. The snapshot is mutable in memory and must be treated as read-only by consumers. It is not live inventory or a carrier connection.

## Typed agent/controller contracts

`emporio_da_musica/contracts/` defines strict Pydantic intents, results, clarification updates, and session state. `emporio_da_musica/providers/` supplies a provider-independent extraction boundary tested with a fake provider. It does not call an LLM or execute business operations yet. See [the contract](docs/CONTRACT.md#implemented-interfaces-and-limits) for payload examples, five-intent limits, missing-quantity behavior, store date handling, and the separation between model proposals and Python-owned identity/prices.

Pydantic validates structure and tzdata supplies the store timezone on all supported platforms. Runtime-only setup uses `.venv/bin/python -m pip install -r requirements.txt`; development setup uses `requirements-dev.txt`, which includes runtime dependencies and pytest/Ruff/pip-tools. No provider credentials are required for the contract tests.

## Catalog search and prices

`emporio_da_musica.catalog.search_catalog(snapshot, ProductSearch(...))` returns a typed result without calling a provider. Search uses case/accent-insensitive substring matching on product names and, separately, category names; repeated whitespace is collapsed and punctuation retained. Both filters must match. No synonyms or fuzzy matching are inferred.

Results are sorted by ascending product ID and limited to ten (raised from five after manual testing showed brand searches such as Yamaha acoustic guitars being truncated). `CatalogData.total_matches` reports the count before truncation: zero matches return `not_found`, while multiple matches return choices without selecting a product. The future controller must save the actual displayed order for ordinal references. An empty search browses the catalog; empty categories have no results.

Availability requires active status and sufficient stock for the requested quantity. Discontinued and coming-soon statuses override positive stock. Only `available_only=True` filters unavailable products. Missing quantity is treated as a unit-price inquiry with an explicit assumption; this default must not be reused for basket assessments.

Active promotions override the 5% PIX discount (manual §§3, 6), including an active 0% promotion. Inactive promotions are ignored. Multiple active promotions on a matching product require confirmation because precedence is undefined. Prices use Decimal and ROUND_HALF_UP to cents per unit, then multiply by quantity. This rounding convention is a prototype assumption. The budget is inclusive and compares the resulting quantity total, using the requested payment method, before result truncation. Unspecified payment uses list/promotional price with an explicit assumption and no PIX discount.

Combined payment requires confirmation. Installments without a method or with a noncredit method request corrected conditions. Credit requests for 2–3 installments return `requires_confirmation` because the policy is ambiguous. Requests for 4–6 installments require at least BRL 80 per installment and 7–12 at least BRL 100 (§3.1), compared against the quote total for the requested quantity after any promotion (credit has no PIX discount). Installments are split in whole cents, with any remainder in the first installment. A count below the minimum is not offered and the response notes the minimum; credit without a count reports the largest eligible count from 4 to 12. No interest is applied, as the manual states. Quotes for unavailable products are informational snapshot prices, not offers or reservations. The separate offline CLI now exposes catalog execution; live provider integration remains subsequent work.

## Local model with Ollama (P08)

Start Ollama with `qwen2.5:3b` installed, then run:

```sh
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:3b
.venv/bin/python -m emporio_da_musica.cli
```

For Windows-hosted Ollama accessed from WSL, use its reachable Windows address instead of localhost. In the current development session, `http://172.21.64.1:11434` was reachable; that address is machine-specific and may change. `--ollama-url` and `--model` override environment variables. `.env.example` documents nonsecret values; files named `.env` are not loaded automatically. No API key or paid API is used. Keep access to the local server restricted to the intended machine/network.

Type natural language, for example “Mostre violões Yamaha”, then “Quero uma unidade do segundo no PIX”. The `--demo` option retains command-based offline behavior. Catalog lookup, supported price calculations, and session-scoped order lookup execute in Python. General policy questions, out-of-scope messages, small talk, and complaints are answered as described in Policy answers and service messages below; return assessments are described in Return assessments below; freight quotes are described in Local freight below.

The official extraction prompt is versioned in `emporio_da_musica/providers/prompts/extraction.md`. It defines the persona, schema vocabulary, trust boundary, missing-fact handling, references, corrections, four behavioral examples, and three contextual-reference examples. The full manual precedes these instructions. This extraction call returns intents only; general-policy prose remains a separate planned route and cannot rewrite operational results.

The adapter uses the standard library with `/api/chat`, a Pydantic-derived JSON schema, nonstreaming output, temperature zero, a 16,384-token context setting, and a 2,048-token generation limit. Only full-turn proposals are permitted when no pending operation exists. History is additionally bounded to the most recent complete messages totaling 8,000 characters. The full reviewed manual text (eight source pages) is bundled as `providers/store_manual.txt`; `--manual` accepts a reviewed UTF-8 replacement limited to 40,000 characters. This is context for extraction, not authorization to execute the manual's services or publish conflicting contacts.

Requests are capped at 180,000 serialized bytes and responses at 256,000 transport bytes / 32,000 extracted-content bytes. The default socket timeout is 120 seconds (`--timeout`, maximum 600); this is a socket-operation timeout, not a total wall-clock deadline. There are no transport retries. The existing extraction boundary permits one schema-repair call, at most two requests per turn. Redirects and environment HTTP proxies are disabled. Errors, incomplete output, and exhausted generation produce a sanitized failure without fallback prices. Source statements and JSON validity do not prove correct interpretation.

Opt-in live smoke evaluation (not collected by pytest or CI):

```sh
.venv/bin/python -m evals.ollama --url http://localhost:11434 --model qwen2.5:3b
```

This uses bundled demonstration records and reports per-case status and latency. With the contextual-reference examples, the latest Qwen run passed all three smoke steps, including PIX totals and quantity correction. Gemma passed search but quoted the wrong product on the second step; its correction step was not executed. Earlier search and quote requests succeeded, while quantity corrections failed semantic checks. The model is configurable; 3B was selected for local operation and modest download size, not a demonstrated quality advantage over alternatives. The same-prompt comparison supports retaining Qwen for this development flow; it does not establish general model superiority. See the recorded live findings in `docs/OLLAMA_EVALUATION.md`.

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

`/buscar` with no query lists the first ten products. `/preco POSITION QUANTITY METHOD` uses the numbered list from the last response; methods are `pix`, `debit`, `credit`, and `boleto`. `/escolher POSITION`, `/quantidade NUMBER`, and `/pagamento METHOD` answer the first pending clarification when that field was requested. `/cancelar` discards unfinished queries, `/ajuda` shows commands, and `/sair`, EOF, or Ctrl+C ends the session. Commands with missing or invalid arguments show usage examples without invoking extraction. Clarification commands without pending work explain how to start a price query; unrequested fields leave pending work unchanged. The demo provider recognizes these explicit commands only; it is not a language model or a natural-language interpreter.

`Controller(snapshot, provider, clock=...)` accepts any provider implementing the existing extraction protocol. `handle(message)` returns deterministic Portuguese text and typed operation results. It validates the complete proposal before dispatch, permits one schema repair, and executes supported catalog/payment-price requests in source order. Payment requests reuse the catalog's supported price rules, require an explicit quantity/payment method, and apply the §3.1 installment bands described above. Order status requests run only for the startup-selected simulated customer (see Order lookup below). Policy questions use a separate model call; out-of-scope, small-talk, and complaint messages use fixed templates. Return assessments and local freight quotes run in Python (see their sections below).

Selections resolve in Python: an ordinal refers to the actual list shown before the current turn; `selected` may use a preceding unique successful lookup. Search results and successful product quotes in a response share one numbering sequence in first-display order (at most 50 distinct products). Ambiguous, failed, or unsuccessful reference resolution clears the current selection. Exact resolved IDs are quoted without another name search, including when names are duplicated. Each successful quote participates in the displayed list, preserving its selection when an independent search also runs. A quote-only response lists the quoted products; subsequent ordinals refer to that updated list.

Missing facts create at most five pending operations. A scoped clarification updates and revalidates only its target; resolved product IDs remain pinned while quantity/payment facts are collected. An unresolved product still requires an explicit reference update even if an independent lookup selected another product. Other pending operations remain suspended until their own clarification; no dependency graph or automatic retry is inferred. A new complete intent turn replaces earlier pending work; `/cancelar` explicitly cancels it. Corrections to already completed requests are new turns and recompute prices. The response shows successes first, limitations next, and one focused clarification last.

Input is limited to 4,000 characters; the CLI drains an oversized line without interpreting its remainder. History retains at most 20 messages in memory. Full operational output is displayed, but responses exceeding the history field limit are represented by a fixed summary in history. Provider requests contain the ordered displayed names and pending hints, never customer tables or session identity. Logs include only operation/error class identifiers; expected arithmetic, record-lookup, and validation failures cannot produce fallback prices. Unexpected programming errors are not silently swallowed. Product text is rendered without terminal control characters. No persistent session, paid API, dependency, or transaction capability is added.

## Prototype policy assumptions

The challenge permits reasonable documented interpretations. For implementation, prefer the detailed installment bands over the payment summary; defer the ambiguous 2–3 installment band and combined-payment calculations for confirmation. Initially support local freight only for a declared Campo Grande/MS destination, using item totals after applicable discounts and before freight; exactly BRL 500 requires confirmation. Other metropolitan destinations, the preference-exchange starting event, and conflicting contact details also require confirmation. These decisions and their source references are detailed in [architecture](docs/ARCHITECTURE.md#policy-decisions-for-implementation-p03--issue-4).

## Policy answers and service messages (P12)

General policy questions (hours, address, payment methods, exchanges, warranty, delivery) use a second Ollama call with the full manual and `providers/prompts/policy.md`. Only text from the customer's current message is sent (the model-isolated question when it appears literally in that message); no history, identity, or order data. The model returns JSON with `covered`, `answer`, and manual section references, validated in Python against the known sections. The answer is displayed with its sections and a footer stating that it is a general explanation, not an individual approval. If the model reports an explicit store-address question (“Qual o endereço da loja?”, “Onde fica a loja?”) as uncovered or fails, the address is shown from fixed manual §1.2 text; the fallback applies only when the whole question is about the store address, so mixed questions, delivery addresses, and order locations keep their normal outcome. Contact requests keep the conflicting-contact message.

Python enforces these limits rather than relying on the prompt:

- `covered: false` (unrelated or unsupported questions) shows the fixed out-of-scope message instead of model prose.
- Contact requests (telefone, WhatsApp, e-mail, contato) are answered without the model, and answers containing contact details (eight or more digits after removing separators, `@`, `arroba`, `ponto com`, `www`, `http`, `wa.me`, `.com`, or the joined store domain) are discarded: the manual lists conflicting contacts, so a fixed message states the conflict and gives the store address.
- Every number in an answer must appear in the manual, so invented prices, discounts, or deadlines are rejected; answers claiming an executed action (registered, approved, refunded, cancelled, forwarded, transferred) are rejected; answers are limited to 1,000 characters.
- Malformed answers, unknown sections, or provider failures show a fixed limitation, never partial prose.
- These guards reduce prompt-injection risk but cannot prove grounding: a spelled-out number or a misstated rule using manual numbers can still pass.
- The command-based demo has no policy model and reports the route as unavailable.

Out-of-scope messages, greetings, thanks, goodbyes, and complaints use fixed Portuguese templates in `composer.py`. Python picks the out-of-scope template from the model's topic (or the current message when it is a single request without a topic): accessory requests (strings, cables, picks, effect pedals, amplifiers, cases, covers; ambiguous words such as “7 cordas”, “cordas orquestrais”, “Cabo Frio”, or “pedal de bateria” are not counted) state that the store sells only instruments and does not recommend other stores; unrelated topics (for example, general knowledge) list what the assistant can help with instead of mentioning accessories. Individual cases (returns, freight, installments) are routed to Python assessments; the policy model only explains general rules and is instructed not to decide individual cases. Complaint replies acknowledge the customer and state that nothing was registered or forwarded. Semantic correctness of policy prose is not proven by these checks; it is evaluated in `docs/OLLAMA_EVALUATION.md`.

A payment or freight quote for a product named in the message shows that product once; the search list is shown only when the name matches several products or the quote fails.

Catalog searches also tolerate observed extraction errors. A product name combined with a wrong model-guessed category is retried by name only, and the response says the search was widened. When a category is given, a search term that does not appear in the current message (for example `viola` invented for “violões”) is dropped, while a typed term such as “violino” is kept. A price limit is applied only when its amount appears in the current message (`1000`, `1.000`, `1.000,50`, `1000.00`, `2 mil`, `mil`); otherwise the response states that the limit was not applied. A quote whose product reference consists only of payment words (for example `débito` or `no cartão`, invented from the payment method) is treated as naming no product, so the assistant asks for the product instead of reporting no match; in a clarification answer, the invented reference is dropped and the other answered facts are applied. Only PIX changes a price, so a model-supplied PIX is accepted only when the current message says `pix` with no negation or other payment term; any doubt asks the customer. Earlier quote facts are reused for the same product with a notice, unless the message mentions payment or names another product. Quantity is not yet checked against the message, and a request to “add” a product quotes it alone, as there is no basket.

## Order lookup (P09)

Start either CLI mode with `--customer-id N` to select a simulated customer from the loaded snapshot, for example:

```sh
.venv/bin/python -m emporio_da_musica.cli --demo --customer-id 1
```

Then use `/pedido 4` in demo mode, or ask in natural language (“Qual o status do meu pedido 4?”). An unknown ID fails startup. The identity is fixed for the session, shown in the banner as a demonstration, and never sent to the model; it is not authentication. Without it, order requests return a fixed message and no record is consulted.

## Local freight (P10)

Freight quotes need the product, quantity, payment method, and a declared destination city, because the BRL 500 threshold (§5.1) is compared with the item subtotal after promotion or PIX discount, before freight. Only Campo Grande/MS (or Campo Grande without a state, labeled as an assumption) is supported: above BRL 500 is free, below costs BRL 35, and exactly BRL 500 requires store confirmation. The manual does not list the metropolitan municipalities, and outside-region prices depend on postal code, weight, and dimensions without a carrier integration, so other cities return a confirmation message with the manual's general transit ranges. A postal code alone never establishes the region, and the customer's recorded city is not used. Unavailable products get no freight, and a failed quote is reported before the destination is requested. Campo Grande without a state but with a postal code outside MS (not 79xxx) requires confirmation. The 1–3 business-day local estimate is labeled as an estimate, never a delivery date.

## Return assessments (P11)

A customer's own return or exchange case (for example, “Me arrependi da minha compra, posso devolver meu pedido?”) is assessed in Python against manual §§4.1–4.4; general questions about the return policy remain policy answers. The assistant asks only for the facts the reason needs: withdrawal needs purchase channel, receipt date, and product condition; defect needs the order number (its 30-day window starts at the recorded order date, so a simulated customer session is required); preference needs the product condition. The response lists each condition as satisfied, not satisfied, not informed, or requiring store review, labeled as a customer declaration, order record, or manual rule. A delivery estimate never counts as receipt, a declared defect always needs store inspection, and the preference window is reported for review because the manual does not state its starting event. No return, exchange, or refund is requested, approved, or performed. See `docs/CONTRACT.md` for the full rules.

Only orders of the session customer are rendered: status, recorded historical total (never recomputed from the current catalog), tracking code when recorded, and the estimated delivery explicitly labeled as an estimate that does not confirm receipt. Missing tracking or estimates are stated as not recorded. Foreign and nonexistent order numbers produce the same response. A request without a number asks for it, or reuses the order shown successfully in the previous lookup. An order number is accepted only when its ASCII digits appear in the current message outside money amounts (such as `R$ 4,00`), so a number copied by the model from history is discarded; numbers written only in words therefore lead to a request for the digits. When the customer typed a number that was not extracted, the order in focus is never used as a substitute. This filter improves extraction quality; access control is the Python ownership check. Rendered order facts (status, recorded total, tracking code, estimate) enter the bounded session history sent to the local model. Items, payment method, customer details, and notes are not displayed. Data is the historical snapshot, not a carrier integration.

Date calculations will use an injected clock in `America/Campo_Grande`, with the starting date as day zero and the final calendar day included. Missing holiday data prevents exact business-day deadlines. These are prototype boundaries, not implemented features, production authentication, or authorization to perform refunds or other transactions.

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

On 2026-11-03, on the list-reference branch, all 463 tests passed locally with Python 3.13.18 and pytest 9.2.0; CI on Windows, Linux, and macOS runs on each pull request. The original six-table snapshot also loaded successfully with the counts listed above. Ruff and `pip check` passed.

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
