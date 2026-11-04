# Empório da Música

A text-based customer service agent for a fictional musical instrument store in Campo Grande/MS, built for the Artefact AI Engineer technical challenge. It runs as a Python CLI with a local model through Ollama. It answers in Portuguese about the catalog, prices, payment, freight, orders, returns, and store policies.

The main design decision is that **the model only interprets; Python decides**. The model proposes structured intents. Python validates them, controls access to orders, applies the business rules, and writes every price, stock fact, and order fact directly.

[Run the agent](#quick-start) · [Conversation examples](#examples) · [Technical decisions](#technical-decisions) · [Limitations](#known-limitations) · [Use of AI](#use-of-coding-assistants)

## Quick start

You need [Python 3.13](https://www.python.org/downloads/) and [Ollama](https://ollama.com/download). No API key or paid service is needed. The model download is about 2 GB.

Use the commands for your terminal. **PowerShell and WSL use different Python paths**; keep a separate project copy and `.venv` for each. After cloning, run commands from the project directory.

**1. Get the code and install the dependencies**

Linux, macOS, or WSL:

```sh
git clone https://github.com/vitaa1/emporio-da-musica.git
cd emporio-da-musica
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
git clone https://github.com/vitaa1/emporio-da-musica.git
cd emporio-da-musica
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2. Download the model** (with Ollama running)

```sh
ollama pull qwen2.5:3b
```

**3. Start the agent**

Linux, macOS, or WSL:

```sh
.venv/bin/python -m emporio_da_musica.cli
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m emporio_da_musica.cli
```

If the agent runs in WSL and Ollama runs on Windows, `localhost` does not reach the server, so pass its address:

```sh
.venv/bin/python -m emporio_da_musica.cli --ollama-url "http://$(ip route | awk '/default/{print $3}'):11434"
```

The agent warns at startup if it cannot reach Ollama or the model is not installed. Type `/sair` to exit.

**4. Type these messages in the agent**

```text
Quero comprar um violão
Yamaha
Quero o segundo
2 unidades no pix
E em 10 vezes no crédito?
Qual o horário de funcionamento no sábado?
```

A broad request gets a question about brand or budget. A list shows names and prices, and a chosen model shows its stock, unit price, and every payment option.

### Check an order

`--customer-id` is optional. It simulates a logged-in customer and is only needed for order lookups. Customer 3 owns order 1 in the demo data. Add it to the command from step 3, then ask `Consulte meu pedido 1`:

Linux, macOS, or WSL:

```sh
.venv/bin/python -m emporio_da_musica.cli --customer-id 3
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m emporio_da_musica.cli --customer-id 3
```

If the agent runs in WSL and Ollama runs on Windows, also include the `--ollama-url` option shown in step 3.

### Run without a model

The offline mode needs no Ollama. It uses explicit commands and does not interpret natural language, so it only checks the rules:

Linux, macOS, or WSL:

```sh
.venv/bin/python -m emporio_da_musica.cli --demo --customer-id 3
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m emporio_da_musica.cli --demo --customer-id 3
```

Once the agent starts, test a catalog search and quote. In `/preco 1 1 pix`, the first `1` selects the first listed product and the second requests one unit. This does not create an order:

```text
/buscar Yamaha
/preco 1 1 pix
```

Separately, consult an existing demo order belonging to customer 3. Order `1` is a historical record, unrelated to the quote above:

```text
/pedido 1
/sair
```

Other commands are listed when the session starts.

## Configuration

| Setting                                  | Flag            | Environment variable | Default                  |
| ---------------------------------------- | --------------- | -------------------- | ------------------------ |
| Ollama address                           | `--ollama-url`  | `OLLAMA_BASE_URL`    | `http://localhost:11434` |
| Model                                    | `--model`       | `OLLAMA_MODEL`       | `qwen2.5:3b`             |
| Socket timeout (seconds, maximum 600)    | `--timeout`     |                      | `120`                    |
| Simulated customer for order lookup      | `--customer-id` |                      | none                     |
| Alternative CSV directory                | `--data-dir`    |                      | `data/demo/`             |
| Alternative manual (reviewed UTF-8 text) | `--manual`      |                      | bundled manual           |

Flags override environment variables. `.env` files are not loaded automatically; `.env.example` lists the variables to export.

For the WSL address shown in the Quick start to work, Ollama on Windows must accept connections from WSL. Keep the server restricted to the intended machine or network.

## Data

The application uses `data/demo/` by default. It keeps the challenge's catalog and order scenarios but replaces customer names, contacts, cities, order notes, and tracking codes with synthetic values, because customer data has no reason to be in a public repository. [The demo README](data/demo/README.md) describes the transformations.

The original CSVs are optional. Use `--data-dir` to select another directory; see [data preparation and validation](data/demo/README.md).

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

See the [architecture document](docs/ARCHITECTURE.md) for modules, contracts, and detailed behavior.

## Technical decisions

| Decision                                                         | Why                                                                                                                                    | Trade-off                                                                         |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Python owns prices, rules, and authorization                     | A wrong price or a leaked order is the costliest failure, and live testing showed the 3B model producing valid JSON with wrong meaning | Responses are less natural, and every new rule needs code                         |
| Model output is intents, not free text, for operational answers  | Critical facts cannot be rewritten or invented by the model                                                                            | Requires a schema and a controller for each operation                             |
| Local Ollama with `qwen2.5:3b`                                   | No cost or credentials, and customer messages stay local. It passed the same-prompt smoke test where Gemma failed on one step          | A small sample, not proof of general superiority; a small model needs more guards |
| No agent framework                                               | One agent with sequential operations is simple enough for a direct controller                                                          | Retries and tool loops would have to be written if the scope grew                 |
| CSVs in memory, no database or vector store                      | The data is small and read-only; the full manual fits in the model context                                                             | Does not scale to a large catalog or manual, and has no live stock                |
| Session-only history                                             | The challenge does not require persistence                                                                                             | Conversations are lost when the CLI closes                                        |
| `--customer-id` set outside the model                            | The model and the message text cannot change whose orders are visible                                                                  | Demonstrates authorization, not real authentication                               |
| `Decimal` for all money                                          | Avoids floating-point errors at policy thresholds                                                                                      | None significant                                                                  |
| Guided purchase questions and payment options composed in Python | Customers get a conversation without letting the model state prices; the small model is not trusted for this text                      | Questions are templates, so the tone varies little                                |
| Ask for confirmation when the manual is ambiguous                | The challenge allows documented assumptions, and an invented commitment is worse than a clarification                                  | Some answers defer to the store                                                   |

### Prompt and retrieval strategy

- **Persona:** the versioned [extraction](emporio_da_musica/providers/prompts/extraction.md) and [policy](emporio_da_musica/providers/prompts/policy.md) prompts set an informal, professional, welcoming store tone, as the manual asks. Fixed Python templates follow the same tone.
- **Data versus policy:** the model classifies each request into a typed intent. Data intents run Python queries, and policy questions go to the manual route, so the model never answers a price or order from memory.
- **Extraction prompt:** it defines the schema vocabulary, the trust boundary, how to handle missing facts, and a few behavioral examples. Temperature is zero and output is constrained by a JSON schema derived from Pydantic.
- **Guards in code:** a prompt instruction is not a guarantee, so important rules are also enforced in Python. For example, payment methods, budgets, and order numbers must appear in the current message.
- **Retrieval:** there are no embeddings. The whole eight-page manual is sent as context, which is simpler and cannot miss a section at this size. Function-calling loops were also avoided: a single validated proposal per turn is easier to test with a small model.

### Policy assumptions

The manual is ambiguous or incomplete in several places. The prototype handles them like this:

- **Installments:** the detailed §3.1 bands take precedence over the summary table: 4–6x requires at least BRL 80 per installment, and 7–12x at least BRL 100. The 2–3x band is quoted when each installment is at least BRL 100, which satisfies every reading of the manual, and requires confirmation below that. Combined payments state the BRL 2,000 threshold, and the split requires confirmation.
- **Rounding:** PIX and promotional unit prices round half-up to cents. Any installment remainder goes in the first installment.
- **Freight:** only Campo Grande/MS is quoted, because the manual does not list the metropolitan municipalities. Exactly BRL 500 requires confirmation, because the manual covers only above and below that value.
- **Preference exchange:** the deadline's starting event is not stated, so the case is reported for store review.
- **Contacts:** the manual gives conflicting phone numbers and emails, so the agent states the conflict and gives the store address.

[The architecture document](docs/ARCHITECTURE.md#policy-decisions) has the source references.

## Examples

Three recorded conversations with `qwen2.5:3b` and synthetic demo data:

| Conversation | What it demonstrates |
| --- | --- |
| [Guided purchase](examples/guided-purchase.md) | Catalog search, product selection, and a two-unit PIX quote |
| [Installments and freight](examples/installments-and-freight.md) | Credit installments, PIX discount, local free shipping, and unsupported destinations |
| [Order access](examples/order-access.md) | Own-order lookup and rejection of an attempt to access another customer's order |

## Testing and evaluation

The project has 761 deterministic tests that need no model or credentials. CI runs them on Linux, Windows, and macOS, together with lint and formatting checks.

The latest recorded full-suite model evaluation passed 49 of 49 automated turn checks across 19 scenarios. This is a development regression suite, not a general accuracy guarantee.

See [test commands and dependency maintenance](docs/DEVELOPMENT.md) and the [evaluation report, including failures and limitations](docs/EVALUATION.md).

## Development

See the [development guide](docs/DEVELOPMENT.md) for platform-specific test commands and dependency generation. Repository conventions are in [AGENTS.md](AGENTS.md).

## Known limitations

- **Catalog browsing is basic.** Lists stop at ten items with no next page, and "preço mais baixo" is not sorted by price. Two filters in one message, such as two brands, are not combined. The guards that correct search terms cover the catalog's main instrument words, not every phrasing.
- **Interpretation errors remain possible.** Quantity is not checked against arbitrary wording, generic "cartão" depends on the model, and negations may trigger an extra clarification.
- **Recommendations are not supported.** "Qual violão para iniciante?" is treated as out of scope rather than answered with a suggestion.
- **Some policy answers ask for too much.** "Posso trocar se não gostar?" asks for an order number before explaining the rule.
- **Routing relies partly on word lists.** Python corrects known routing mistakes for policy topics, promotions, and instruments outside the catalog, so other wording can still be misrouted. When the model marks a policy answer as uncovered, only a reviewed summary is shown, so some valid questions get the out-of-scope message. Two questions in one message can lose one if the model proposes a single intent.
- **The model can invent a selection.** A list position or quantity it proposes is not checked against the message, so a quote can refer to a product the customer did not pick. Spelling correction covers brand names only, and short name fragments can match inside longer words.
- **Fixed answers cover clear questions only.** Common questions about payment methods, installments, refunds, return freight, mouthpieces, carrier deadlines, transport damage, price holds, campaign dates, and data deletion use reviewed text without the model. Other wording still depends on the model and can ask for facts already given.
- **Policy prose is not proven correct.** Validators reject invented numbers, unknown sections, and claims of executed actions, but a misstated rule using valid numbers can pass. Warranty, store-hours, return-deadline, and discount-stacking questions use fixed reviewed summaries when they match.
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

**Workflow.** The assistants worked on one issue and branch at a time: plan from the project documents, implement with offline tests, run the real model, review, fix confirmed findings, then update the documentation. The reviewer roles and skills used are versioned in `.codex/agents/` and `.agents/skills/`, and `AGENTS.md` holds the working rules.

Running the real model changed the design. The small model often returned valid JSON with the wrong meaning, such as order numbers copied from history, so those cases became checks in Python. The failures are preserved in [the evaluation report](docs/EVALUATION.md).

## Further documentation

- [Architecture, policy decisions, contracts, and feature behavior](docs/ARCHITECTURE.md)
- [Evaluation report](docs/EVALUATION.md)
