# Empório da Música

A text-based customer service agent for a fictional musical instrument store in Campo Grande/MS, built for the Artefact AI Engineer technical challenge. It runs as a Python CLI with a local model through Ollama. It answers in Portuguese about the catalog, prices, payment, freight, orders, returns, and store policies.

The main design decision is that **the model only interprets; Python decides**. The model proposes structured intents. Python validates them, controls access to orders, applies the business rules, and writes every price, stock fact, and order fact directly.

## Quick start

Requirements: Python 3.13 and, for natural-language mode, [Ollama](https://ollama.com/). No API key or paid service is needed.

```sh
git clone https://github.com/vitaa1/emporio-da-musica.git
cd emporio-da-musica
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, create the environment with `py -3.13 -m venv .venv` and use `.\.venv\Scripts\python.exe` in the commands below. To install Python 3.13 with uv, see the [development guide](docs/DEVELOPMENT.md).

### Run with the local model

```sh
ollama pull qwen2.5:3b
.venv/bin/python -m emporio_da_musica.cli --customer-id 3
```

On WSL with Ollama running on Windows, `localhost` does not reach the server: add the `--ollama-url` shown under [Configuration](#configuration). The agent warns at startup when it cannot reach the server or the model is not installed.

Then try:

```text
Quero comprar um violão
Yamaha
Quero o segundo
2 unidades no pix
E em 10 vezes no crédito?
Consulte meu pedido 1
Qual o horário de sábado?
```

A broad request gets a question about brand or budget. A list shows names and prices, and a chosen model shows its stock, unit price, and every payment option.

### Run without a model

The offline mode uses explicit commands and does not interpret natural language. It is useful for checking the rules without Ollama:

```sh
.venv/bin/python -m emporio_da_musica.cli --demo --customer-id 3
```

```text
/buscar Yamaha
/preco 1 1 pix
/pedido 1
/sair
```

Other commands are listed when the session starts.

## Configuration

| Setting | Flag | Environment variable | Default |
| --- | --- | --- | --- |
| Ollama address | `--ollama-url` | `OLLAMA_BASE_URL` | `http://localhost:11434` |
| Model | `--model` | `OLLAMA_MODEL` | `qwen2.5:3b` |
| Socket timeout (seconds, maximum 600) | `--timeout` | | `120` |
| Simulated customer for order lookup | `--customer-id` | | none |
| Alternative CSV directory | `--data-dir` | | `data/demo/` |
| Alternative manual (reviewed UTF-8 text) | `--manual` | | bundled manual |

Flags override environment variables. `.env` files are not loaded automatically; `.env.example` lists the variables to export.

When Ollama runs on Windows and the agent runs in WSL, use the Windows host address rather than `localhost`:

```sh
.venv/bin/python -m emporio_da_musica.cli --ollama-url "http://$(ip route | awk '/default/{print $3}'):11434"
```

Ollama must accept connections from WSL for this to work. Keep the server restricted to the intended machine or network.

## Data

The application uses `data/demo/` by default. It keeps the challenge's catalog and order scenarios but replaces customer names, contacts, cities, order notes, and tracking codes with synthetic values, because customer data has no reason to be in a public repository. [The demo README](data/demo/README.md) describes the transformations.

To validate a directory holding the original six CSVs (this prints table counts only):

```sh
.venv/bin/python -m emporio_da_musica /path/to/challenge/data
```

## Architecture

```text
Customer message
      │
      ▼
Local model ── proposes intents as JSON
      │
      ▼
Pydantic ───── validates the structure (one repair attempt)
      │
      ▼
Controller ─── resolves references, checks evidence and access
      │
      ▼
Business rules and in-memory CSV queries
      │
      ▼
Python composer ── writes prices, stock, orders, errors, and clarifications
```

General policy questions take a separate route: a second model call receives the manual and only the customer's current question. Its answer is validated before display and is shown with its manual sections.

| What | Where |
| --- | --- |
| Intents and results | `emporio_da_musica/contracts/` |
| CSV loading and validation | `emporio_da_musica/data/` |
| Model adapters, prompts, and policy validation | `emporio_da_musica/providers/` |
| Orchestration | `emporio_da_musica/controller.py` |
| Catalog and payment rules | `emporio_da_musica/catalog.py` |
| Return assessments | `emporio_da_musica/returns.py` |
| Response templates | `emporio_da_musica/composer.py` |
| Terminal interface | `emporio_da_musica/cli.py` |

## Technical decisions

| Decision | Why | Trade-off |
| --- | --- | --- |
| Python owns prices, rules, and authorization | A wrong price or a leaked order is the costliest failure, and live testing showed the 3B model producing valid JSON with wrong meaning | Responses are less natural, and every new rule needs code |
| Model output is intents, not free text, for operational answers | Critical facts cannot be rewritten or invented by the model | Requires a schema and a controller for each operation |
| Local Ollama with `qwen2.5:3b` | No cost or credentials, and customer messages stay local. It passed the same-prompt smoke test where Gemma failed on one step | A small sample, not proof of general superiority; a small model needs more guards |
| No agent framework | One agent with sequential operations is simple enough for a direct controller | Retries and tool loops would have to be written if the scope grew |
| CSVs in memory, no database or vector store | The data is small and read-only; the full manual fits in the model context | Does not scale to a large catalog or manual, and has no live stock |
| Session-only history | The challenge does not require persistence | Conversations are lost when the CLI closes |
| `--customer-id` set outside the model | The model and the message text cannot change whose orders are visible | Demonstrates authorization, not real authentication |
| `Decimal` for all money | Avoids floating-point errors at policy thresholds | None significant |
| Guided purchase questions and payment options composed in Python | Customers get a conversation without letting the model state prices; the small model is not trusted for this text | Questions are templates, so the tone varies little |
| Ask for confirmation when the manual is ambiguous | The challenge allows documented assumptions, and an invented commitment is worse than a clarification | Some answers defer to the store |

### Prompt and retrieval strategy

- **Persona:** the versioned [extraction](emporio_da_musica/providers/prompts/extraction.md) and [policy](emporio_da_musica/providers/prompts/policy.md) prompts set an informal, professional, welcoming store tone, as the manual asks. Fixed Python templates follow the same tone.
- **Data versus policy:** the model classifies each request into a typed intent. Data intents run Python queries, and policy questions go to the manual route, so the model never answers a price or order from memory.
- **Extraction prompt:** it defines the schema vocabulary, the trust boundary, how to handle missing facts, and a few behavioral examples. Temperature is zero and output is constrained by a JSON schema derived from Pydantic.
- **Guards in code:** a prompt instruction is not a guarantee, so important rules are also enforced in Python. For example, payment methods, budgets, and order numbers must appear in the current message.
- **Retrieval:** there are no embeddings. The whole eight-page manual is sent as context, which is simpler and cannot miss a section at this size. Function-calling loops were also avoided: a single validated proposal per turn is easier to test with a small model.

### Policy assumptions

The manual is ambiguous or incomplete in several places. The prototype handles them like this:

- **Installments:** the detailed §3.1 bands take precedence over the summary table: 4–6x requires at least BRL 80 per installment, and 7–12x at least BRL 100. The 2–3x band and combined payments require confirmation.
- **Rounding:** PIX and promotional unit prices round half-up to cents. Any installment remainder goes in the first installment.
- **Freight:** only Campo Grande/MS is quoted, because the manual does not list the metropolitan municipalities. Exactly BRL 500 requires confirmation, because the manual covers only above and below that value.
- **Preference exchange:** the deadline's starting event is not stated, so the case is reported for store review.
- **Contacts:** the manual gives conflicting phone numbers and emails, so the agent states the conflict and gives the store address.

[The architecture document](docs/ARCHITECTURE.md#policy-decisions-for-implementation-p03--issue-4) has the source references.

## Examples

[Five recorded conversations](docs/EXAMPLE_CONVERSATIONS.md) show real, verbatim model runs: catalog references with quantity and payment changes, installments with freight, order access with an injection attempt, grounded policy answers, and a promotion that does not stack with PIX.

## Testing and evaluation

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

The 535 deterministic tests need no model or credentials. They run in CI on Linux, Windows, and macOS.

On 2026-11-03, a clean copy of this documentation's working tree was verified on WSL2 with Python 3.13 in a new virtual environment: installing the pins, the data validation, the offline commands, and the model example under Quick start all worked, as did the checks above. A single example run does not guarantee identical model output later.

Model behavior is evaluated separately, because it depends on a local server and is not deterministic:

```sh
.venv/bin/python -m evals.suite --url http://localhost:11434 --output /tmp/emporio-evaluation.json
```

The latest recorded run passed 36 of 36 turns across 15 scenarios. The cases were informed by development, so this is a regression check rather than an independent accuracy measure. [The evaluation report](docs/AGENT_EVALUATION.md) keeps the earlier failing runs and their corrections, including one provider error whose cause was not determined.

## Known limitations

- **Catalog browsing is basic.** Lists stop at ten items with no next page, and "preço mais baixo" is not sorted by price. Two filters in one message, such as two brands, are not combined. The guards that correct search terms cover the catalog's main instrument words, not every phrasing.
- **Interpretation errors remain possible.** Quantity is not checked against arbitrary wording, generic "cartão" depends on the model, and negations may trigger an extra clarification.
- **Policy prose is not proven correct.** Validators reject invented numbers, unknown sections, and claims of executed actions, but a misstated rule using valid numbers can pass. Only warranty-only answers use a fixed reviewed summary.
- **No transactions.** There is no basket, purchase, refund, or human handoff. "Adicione" quotes only the named product, and complaints are acknowledged with a clear statement that nothing was registered.
- **No live data.** Stock and orders come from a snapshot, and there is no carrier integration. Freight outside Campo Grande is not quoted.
- **No real authentication.** The customer identity is simulated.
- **Dates are limited.** The model does not know today's date; Python resolves only supported relative dates such as "hoje" and "ontem". Holidays are unknown, so exact business-day deadlines are not calculated.
- **The evaluation is small.** It gives no stability guarantee between runs, and token use and model digest were not recorded.

## Possible improvements

1. Grow the evaluation with held-out cases and repeated runs, then use it to compare larger models.
2. Add a real complaint and human handoff channel.
3. Connect live stock, a carrier, and real customer authentication.
4. Add a basket, so that "adicione" and multi-item freight work.
5. Retrieve manual sections by topic if the manual outgrows the model context.
6. Get store answers to the open policy questions and remove the matching confirmations.

## Use of coding assistants

I used two assistants, and they wrote most of the code and documentation:

- **Codex CLI** did most of the development: requirements and source analysis, planning, architecture and contract drafts, implementation, and tests.
- **Claude Code** was used mainly for reviews and for adjusting the last implementations, and it also drafted this README.

**My part.** The architecture and the scope are my decisions: the CLI → model → Python controller flow, Python-owned business rules, few-shot prompting, explicit guardrails, and problem decomposition. I reviewed and manually tested the work throughout, and I merged every pull request. I did not read every diff line by line, so I also relied on automated tests, CI, and review passes to check the code.

**Workflow.** The assistants worked on one issue and branch at a time: plan from `docs/`, implement with offline tests, run the real model, review, fix confirmed findings, then update the documentation. The reviewer roles and skills used are versioned in `.codex/agents/` and `.agents/skills/`, and `AGENTS.md` holds the working rules.

Running the real model changed the design. The small model often returned valid JSON with the wrong meaning, such as order numbers copied from history, so those cases became checks in Python. The failures are preserved in [the Ollama evaluation](docs/OLLAMA_EVALUATION.md) and [the agent evaluation](docs/AGENT_EVALUATION.md).

## Further documentation

- [Architecture and policy decisions](docs/ARCHITECTURE.md)
- [Agent–controller contract](docs/CONTRACT.md)
- [Detailed behavior reference](docs/BEHAVIOR.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Project plan](docs/GITHUB_PLAN.md) and [handoff history](CONTEXT.md)
