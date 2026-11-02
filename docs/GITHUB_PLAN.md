# GitHub Milestones and Issues

Ready-to-copy planning draft, 2026-11-02. The user will create/update milestones and issues manually. Some entries have since been registered on GitHub: setup is issue #1 (closed), P01 is #5 (closed after PR #6), P02 is #3 (closed after PR #13), and P03 is #4. Recheck remote status before further updates. Labels and `P01`–`P14` are local planning suggestions, not actual GitHub issue numbers. Existing issue numbers/statuses must be checked before registering duplicates. Dates are intentionally unset until the recruitment deadline is known.

## Milestones

| Milestone | Outcome / completion condition | Issues |
| --- | --- | --- |
| M0 — Development foundation | Reproducible environment, formatting/linting, and documented local checks. Reuse the existing preparation milestone. | Existing completed Python setup; P01–P02 |
| M1 — Data and domain contracts | Validated in-memory data, documented policy decisions, typed controller interfaces. | P03–P05 |
| M2 — Working CLI agent | A real model handles catalog and order requests through the controller and deterministic composer. | P06–P09 |
| M3 — Policy and service coverage | Payment, freight, returns, general policies, and multi-intent clarification flows are covered. | P10–P12 |
| M4 — Evaluation and submission | Reproducible evaluations, real demonstrations, complete README, and final delivery verification. | P13–P14 |

Suggested order: P01 → P02 → P03 → P04 → P05 → P06 → P07 → P08 → P09 → P10 → P11 → P12 → P13 → P14. Dependencies below identify actual blockers; do not add tools or infrastructure merely to make milestones larger.

The earlier preparation plan included EditorConfig/Ruff, VS Code configuration, and setup validation. P01 covers tooling; P02 consolidates setup validation and minimal optional editor configuration. Reuse/update existing issues rather than opening replacements blindly.

## Shared definition of done

- One focused branch and PR per issue; no commits, pushes, or GitHub mutations without user authorization.
- Behavior matches the architecture and contract, or changes to those documents accompany it.
- Relevant tests pass; required existing CI checks remain green. New application tests must run without paid provider credentials.
- README/setup changes accompany new commands or dependencies. Generated dependency files are updated through the agreed reference environment, never by hand.
- PR describes behavior, verification, known limits, and its issue link. No secrets or unnecessary customer information in fixtures, examples, logs, or screenshots.
- For documentation-only work, verify consistency and links; do not add application tests just to test prose.

## P01 — Configure EditorConfig, Ruff, and dependency generation

Milestone: M0. Suggested labels: `chore`, `ci`. Dependencies: existing Python setup.

**Scope:** Resolve Windows versus WSL as the lock-generation reference, then configure EditorConfig and Ruff.

Implementation decision: Linux/WSL with Python 3.13 is the generation reference; README and CI change together. EditorConfig, Ruff, and generated pins were merged in PR #6; issue #5 is closed. All three platform checks passed on the merge commit. The existing Windows/Linux/macOS check names are preserved.

**Acceptance criteria**
- [x] Reference environment decision is documented and reflected consistently in README and CI.
- [x] Formatting/linting commands and configuration exist and pass on the repository.
- [x] Development dependencies are pinned through pip-tools; existing setup checks pass.
- [x] No application framework or unrelated tooling is added.

## P02 — Verify and document the contributor workflow

Milestone: M0. Suggested label: `docs`. Dependency: P01.

**Scope:** Validate setup from a clean environment and document WSL use, lint commands, and minimal editor guidance. Keep VS Code configuration optional and free of machine-specific paths.

Local verification completed on 2026-11-02; see README for the environment, commands, results, and limitations. Documentation was merged in PR #13; issue #3 is closed.

**Acceptance criteria**
- [x] Documented setup is executed successfully and its verification is recorded.
- [x] README, AGENTS.md, and CONTEXT.md agree about implemented tooling.
- [x] Remaining setup limitations are explicit; no unimplemented application commands are advertised.

## P03 — Record policy interpretations and supported operations

Milestone: M1. Suggested labels: `docs`, `domain`. Dependencies: none beyond source analysis.

**Scope:** Resolve or explicitly defer installment ambiguity, exact BRL 500 freight, supported delivery regions, conflicting contacts, preference-exchange timing, and simulated customer identity. Use documented reasonable assumptions where appropriate; do not block unrelated work on every ambiguity.

Local documentation completed on 2026-11-02 in `docs/ARCHITECTURE.md`. Source references were checked against the original eight-page manual; its ambiguities remain explicitly deferred. Merged through PR #15; GitHub issue #4 is closed.

**Acceptance criteria**
- [x] Each ambiguity has a source reference, chosen behavior, rationale, and limitation.
- [x] Supported versus confirmation-only/unavailable cases are listed.
- [x] Store timezone, clock injection, and missing holiday/calendar behavior are defined.
- [x] No unsupported claim of real authentication, live data, refund, or complaint routing appears in the scope.

## P04 — Load and validate the supplied CSV data in memory

Milestone: M1. Suggested labels: `feature`, `data`. Dependency: P02.

**Scope:** Introduce the package layout and repeatable source-data loading using the standard CSV library. Preserve originals, validate records and relationships, and build in-memory indexes. Add pytest and focused loader tests.

Implemented locally for GitHub issue #7 on `feature/csv-loader`. The original snapshot loads successfully; 44 synthetic tests, Ruff, and pip check pass. Pytest 9.2.0 and generated pins are included; CI runs deterministic tests on all three platforms. Review/publication and remote CI results remain pending.

**Acceptance criteria**
- [x] All six tables load with expected relationships; invalid required records produce clear errors.
- [x] Amounts, quantities, dates, JSON specs, and optional order fields are normalized explicitly.
- [x] Tests cover duplicate IDs, orphan references, malformed values, and allowed missing fields using small synthetic fixtures.
- [x] Data location and reproducible preparation are documented; no developer-specific absolute path is required.
- [x] No SQLite or external data service is introduced.

## P05 — Implement typed intents, results, and session contracts

Milestone: M1. Suggested labels: `feature`, `architecture`. Dependencies: P03, P04.

**Scope:** Implement Pydantic discriminated intents, typed operation results, clarification updates, and session state from CONTRACT.md. Introduce a minimal provider boundary usable by a fake in tests.

**Acceptance criteria**
- [ ] Unknown fields/types and unauthorized identity/price inputs are rejected.
- [ ] Intent bounds, quantity defaults, relative dates, and clarification payloads are explicitly defined.
- [ ] Pending state, customer-declared facts, and verified records remain distinct.
- [ ] Contract tests cover valid payloads, malformed responses, and attempted state injection.
- [ ] Required runtime/development dependency outputs are generated and documented.

## P06 — Implement catalog search and deterministic price rules

Milestone: M2. Suggested labels: `feature`, `domain`. Dependencies: P04, P05.

**Scope:** Search names/categories with documented case/accent normalization; compute availability and active promotion/PIX pricing. Bound displayed results and preserve their ordering for follow-up selections.

**Acceptance criteria**
- [ ] Active stock, zero stock, discontinued stock, and coming-soon stock produce correct distinct results.
- [ ] Inactive promotions are ignored; PIX never stacks with a promotion.
- [ ] Budget filtering uses the requested payment condition and consistent rounding.
- [ ] No-result and ambiguous matches are distinguishable; arbitrary fuzzy matching infrastructure is not required.
- [ ] Unit tests cover the known dataset edge cases and monetary calculations.

## P07 — Build the controller, CLI, and deterministic composer

Milestone: M2. Suggested label: `feature`. Dependencies: P05, P06.

**Scope:** Complete a catalog conversation end to end using a fake provider first. Implement bounded input, session state, structured validation, clarification, sequential execution, and deterministic result rendering.

**Acceptance criteria**
- [ ] CLI starts/exits cleanly and supports successive messages in one session.
- [ ] Product selection and corrections resolve against actual displayed records.
- [ ] Invalid model output executes no operation; repair is bounded and errors are handled.
- [ ] Independent intents can succeed while dependent ones await clarification.
- [ ] Prices, stock, errors, and follow-up questions are composed without model rewriting.
- [ ] Controller tests run offline with fake provider responses.

## P08 — Select and integrate one LLM provider

Milestone: M2. Suggested labels: `feature`, `evaluation`. Dependency: P07.

**Scope:** Select one model/provider based on representative extraction quality, cost, and setup; connect it to the existing boundary. Add persona, structured-output instructions, full reviewed manual context, and three or four behavioral examples.

**Acceptance criteria**
- [ ] Model choice and observed tradeoffs are documented; model name is configurable.
- [ ] A real CLI catalog query and follow-up work through the controller.
- [ ] Secrets use environment variables and a nonsecret example configuration.
- [ ] Context size/history bounds, timeout, retry limits, and provider-error behavior are explicit.
- [ ] Prompt examples do not supply authoritative current prices or identity claims.
- [ ] Live checks are explicit opt-in operations, separate from credential-free CI.

## P09 — Add session-scoped order lookup

Milestone: M2. Suggested labels: `feature`, `domain`. Dependencies: P03, P07; real demonstration also needs P08.

**Scope:** Query orders and items using the simulated authorized session; render status and available tracking/estimate data.

**Acceptance criteria**
- [ ] Customer identity is established outside model-controlled fields and clearly labeled as simulated.
- [ ] Foreign order access is blocked without leaking order existence or personal data.
- [ ] Historical totals are preserved; missing tracking/estimate fields are not fabricated.
- [ ] Estimates are labeled as estimates and never treated as actual receipt dates.
- [ ] Tests cover accessible, inaccessible, nonexistent, and incomplete orders.

## P10 — Add payment options and supported freight calculations

Milestone: M3. Suggested labels: `feature`, `domain`. Dependencies: P03, P06, P07.

**Scope:** Implement installment rules only as documented, supported local freight, and explicit limitations for unsupported destinations/combined payment/special quotations.

**Acceptance criteria**
- [ ] Installment count, minimum amount, rounding, quantity, and payment-method compatibility are tested.
- [ ] Freight boundary tests include below, exactly, and above BRL 500.
- [ ] Delivery-region membership and freight subtotal basis are documented, not inferred by the model.
- [ ] No exact external freight quote or calendar delivery date is fabricated.
- [ ] Ambiguous/unsupported conditions return the agreed confirmation/unavailable states.

## P11 — Add return assessment and missing-fact workflows

Milestone: M3. Suggested labels: `feature`, `domain`. Dependencies: P03, P07, P09.

**Scope:** Implement supported withdrawal, defect, and preference assessments, preserving distinct policy processes and source references.

**Acceptance criteria**
- [ ] Required facts vary with the request; general questions do not demand an order unnecessarily.
- [ ] Actual receipt, purchase channel, condition, and exclusions remain unknown until supplied or verified.
- [ ] Date-boundary tests use an injected clock; estimates cannot substitute for receipt.
- [ ] Customer declarations are labeled as such and do not authorize a transaction.
- [ ] Ambiguous conditions request confirmation; no refund/cancellation action is claimed.

## P12 — Add grounded policy explanations and service fallbacks

Milestone: M3. Suggested labels: `feature`, `evaluation`. Dependencies: P03, P08, P10, P11.

**Scope:** Enable controller-selected general-policy prose, section references, out-of-scope redirection, small talk, and complaint acknowledgment. Keep critical data blocks in Python.

**Acceptance criteria**
- [ ] Policy-reference validation exists, with explicit acknowledgment that it does not prove semantic correctness.
- [ ] Individual policy decisions route to Python; free-form policy prose cannot bypass required assessment.
- [ ] Accessory requests and unrelated topics are redirected appropriately.
- [ ] Complaints receive empathy and an honest next step without false registration or transfer claims.
- [ ] Known policy ambiguities and provider failures have stable fallbacks.
- [ ] Mixed requests preserve independent answers and focused clarification.

## P13 — Evaluate the complete agent and extend CI

Milestone: M4. Suggested labels: `test`, `evaluation`, `ci`. Dependencies: P09–P12.

**Scope:** Consolidate offline regression tests and a small versioned live-model evaluation set, distinct from few-shot examples. Run and report real results rather than relying on illustrative answers.

**Acceptance criteria**
- [ ] CI runs lint and deterministic tests without provider credentials, preserving existing setup checks.
- [ ] Evaluations cover extraction, grounding, multi-intent dependencies, references, missing facts, out-of-scope handling, injection attempts, and failures.
- [ ] Critical deterministic scenarios pass: no stacked discount, unauthorized order disclosure, invented receipt, or false executed action.
- [ ] Live report records model/configuration, date, cases, results, known failures, and latency/usage when available.
- [ ] No unsupported claim of perfect reliability or arbitrary coverage target is used; observed failures are fixed or documented before delivery.

## P14 — Prepare demonstrations, README, and submission

Milestone: M4. Suggested labels: `docs`, `delivery`. Dependency: P13.

**Scope:** Produce the required deliverables and verify a clean checkout can reproduce the application. Freeze changes at the recruitment deadline.

**Acceptance criteria**
- [ ] README includes actual commands, provider configuration, architecture decisions, limitations, and next improvements.
- [ ] README discloses Codex usage for requirements analysis, planning, and any subsequent implementation/testing assistance actually used.
- [ ] Three to five real conversation transcripts cover varied cases including a nontrivial rule/data operation; redact unnecessary customer data.
- [ ] Fresh-environment execution is verified; examples match implemented behavior.
- [ ] Public repository visibility, incremental history, passing checks, and deadline are verified by the user before submission.
- [ ] User sends the repository link through the requested email channel; no automated sending is implied.

## Requirement coverage

| Requirement | Primary evidence |
| --- | --- |
| Python text agent and runnable interface | P04, P07, P08 |
| Store persona and contextual answers | P08, P12 |
| Operational queries versus policies | P06, P09–P12 |
| Out-of-scope handling | P12, P13 |
| Public repository and incremental development | Shared definition of done, P14 |
| Reproducible README and technical rationale | P02, P08, P14 |
| Limitations and AI-use disclosure | P14 |
| Three to five actual conversations | P14 |

If time becomes tight, reduce optional breadth before sacrificing a working end-to-end agent: retain catalog, orders, general policies, clear missing-information behavior, and at least one well-tested policy application. Keep unsupported cases explicit. Do not spend delivery time adding deployment, databases, multiple agents, or sophisticated retrieval without a demonstrated need.
