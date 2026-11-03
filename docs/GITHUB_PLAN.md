# GitHub Milestones and Issues

Ready-to-copy planning draft, 2026-11-02. The user will create/update milestones and issues manually. Some entries have since been registered on GitHub: setup is issue #1 (closed), P01 is #5 (closed after PR #6), P02 is #3 (closed after PR #13), and P03 is #4, P08 is #11 (closed after PR #26), P09 is #12 (closed after PR #28), P10 is #18 (closed after PR #32), P11 is #19 (closed after PR #30), P12 is #20 (closed after PRs #29 and #33), P13 is #21, and P14 is #22. Recheck remote status before further updates. Labels and `P01`–`P14` are local planning suggestions, not actual GitHub issue numbers. Existing issue numbers/statuses must be checked before registering duplicates. Dates are intentionally unset until the recruitment deadline is known.

## Milestones

| Milestone | Outcome / completion condition | Issues |
| --- | --- | --- |
| M0 — Development foundation | Reproducible environment, formatting/linting, and documented local checks. Reuse the existing preparation milestone. | Existing completed Python setup; P01–P02 |
| M1 — Data and domain contracts | Validated in-memory data, documented policy decisions, typed controller interfaces. | P03–P05 |
| M2 — Working CLI agent | A real model handles catalog and order requests through the controller and deterministic composer. | P06–P09 |
| M3 — Policy and service coverage | Payment, freight, returns, general policies, and multi-intent clarification flows are covered. | P10–P12 |
| M4 — Evaluation and submission | Reproducible evaluations, real demonstrations, complete README, and final delivery verification. | P13–P14 |

Suggested order: P01 → P02 → P03 → P04 → P05 → P06 → P07 → P08 → P09 → P10 → P11 → P12 → P13 → P14. Dependencies below identify actual blockers; do not add tools or infrastructure merely to make milestones larger.

Revised order after the 2026-11-03 requirement review: P09 → P12 (minimal slice) → P10 → P11 → remaining P12 → P13 → P14. The assignment's mandatory behaviors include answering policy questions (hours, address, payments, exchanges) and handling out-of-scope messages, which currently return `OPERATION_NOT_SUPPORTED`. The minimal P12 slice covers general `policy_question` answers grounded in the manual with section references, out-of-scope/accessory redirection, and small talk. Case-specific payment, freight, and return assessments remain in P10/P11 and must not be bypassed by general policy prose. If time becomes tight, reduce P10/P11 breadth rather than the minimal P12 slice.

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

Merged through PR #16 at `b2d7e8f`; issue #7 is closed. Original and bundled demonstration snapshots load successfully. All 46 tests and the three platform CI checks passed.

**Acceptance criteria**
- [x] All six tables load with expected relationships; invalid required records produce clear errors.
- [x] Amounts, quantities, dates, JSON specs, and optional order fields are normalized explicitly.
- [x] Tests cover duplicate IDs, orphan references, malformed values, and allowed missing fields using small synthetic fixtures.
- [x] Data location and reproducible preparation are documented; no developer-specific absolute path is required.
- [x] No SQLite or external data service is introduced.

## P05 — Implement typed intents, results, and session contracts

Milestone: M1. Suggested labels: `feature`, `architecture`. Dependencies: P03, P04.

**Scope:** Implement Pydantic discriminated intents, typed operation results, clarification updates, and session state from CONTRACT.md. Introduce a minimal provider boundary usable by a fake in tests.

Merged through PR #17 at `84ee5ae`, completing M1 as confirmed by the user. Includes 75 contract tests plus the existing 46; runtime/development pins, CI regeneration, and documentation are updated.

**Acceptance criteria**
- [x] Unknown fields/types and unauthorized identity/price inputs are rejected.
- [x] Intent bounds, quantity defaults, relative dates, and clarification payloads are explicitly defined.
- [x] Pending state, customer-declared facts, and verified records remain distinct.
- [x] Contract tests cover valid payloads, malformed responses, and attempted state injection.
- [x] Required runtime/development dependency outputs are generated and documented.

## P06 — Implement catalog search and deterministic price rules

Milestone: M2. Suggested labels: `feature`, `domain`. Dependencies: P04, P05.

**Scope:** Search names/categories with documented case/accent normalization; compute availability and active promotion/PIX pricing. Bound displayed results and preserve their ordering for follow-up selections.

Merged through PR #23 at `4df666e`; issue #9 is complete. Includes 32 catalog tests (153 total at that stage). Search/rounding conventions and payment-stage limitations are documented in README.

**Acceptance criteria**
- [x] Active stock, zero stock, discontinued stock, and coming-soon stock produce correct distinct results.
- [x] Inactive promotions are ignored; PIX never stacks with a promotion.
- [x] Budget filtering uses the requested payment condition and consistent rounding.
- [x] No-result and ambiguous matches are distinguishable; arbitrary fuzzy matching infrastructure is not required.
- [x] Unit tests cover the known dataset edge cases and monetary calculations.

## P07 — Build the controller, CLI, and deterministic composer

Milestone: M2. Suggested label: `feature`. Dependencies: P05, P06.

**Scope:** Complete a catalog conversation end to end using a fake provider first. Implement bounded input, session state, structured validation, clarification, sequential execution, and deterministic result rendering.

Merged through PR #24 at `7abdaf5`; issue #10 is complete. Includes 39 offline controller/CLI tests (192 total). README documents demo commands, reference ordering, pending-work replacement, and deferred real-provider/order/policy behavior.

Before P08, the user requested a small package reorganization on `refactor/package-organization`: separate CSV records/loading and provider interfaces/extraction/demo, and split controller/CLI/rendering tests. This preserves behavior and all 192 tests; it adds no milestone capability or dependency.

**Acceptance criteria**
- [x] CLI starts/exits cleanly and supports successive messages in one session.
- [x] Product selection and corrections resolve against actual displayed records.
- [x] Invalid model output executes no operation; repair is bounded and errors are handled.
- [x] Independent intents can succeed while dependent ones await clarification.
- [x] Prices, stock, errors, and follow-up questions are composed without model rewriting.
- [x] Controller tests run offline with fake provider responses.

## P08 — Select and integrate one LLM provider

Milestone: M2. Suggested labels: `feature`, `evaluation`. Dependency: P07.

**Scope:** Select one model/provider based on representative extraction quality, cost, and setup; connect it to the existing boundary. Add persona, structured-output instructions, full reviewed manual context, and three or four behavioral examples.

Merged through PR #26 at `6858b10`; issue #11 is closed and all three platform checks passed. Implemented with Ollama and configurable `qwen2.5:3b`. The natural-language CLI, full extracted manual, structured schemas, offline adapter tests, and opt-in live evaluation exist. The final contextual-reference prompt passed the three-turn Qwen development evaluation, including quantity correction; earlier semantic failures and the Gemma comparison are retained in the report. The review error-handling fixes pass all 209 offline tests. See OLLAMA_EVALUATION.md.

**Acceptance criteria**
- [x] Model choice and observed tradeoffs are documented; model name is configurable.
- [x] A real CLI catalog query and follow-up work through the controller. With contextual-reference examples, Qwen passed search, quote, and quantity correction with expected totals; Gemma selected the wrong product. See the development evaluation and its limits.
- [x] Secrets use environment variables and a nonsecret example configuration.
- [x] Context size/history bounds, timeout, retry limits, and provider-error behavior are explicit.
- [x] Prompt examples do not supply authoritative current prices or identity claims.
- [x] Live checks are explicit opt-in operations, separate from credential-free CI.

## P09 — Add session-scoped order lookup

Milestone: M2. Suggested labels: `feature`, `domain`. Dependencies: P03, P07; real demonstration also needs P08.

**Scope:** Query orders and items using the simulated authorized session; render status and available tracking/estimate data.

Merged through PR #28 at `c62720b`; issue #12 is closed. Implemented: `--customer-id` startup identity, Python-side authorization, nonrevealing not-found responses, deterministic rendering, `/pedido` demo command, and prompt examples. Order items are not rendered. A quote clarification fix keeps declared quantity when the model answers with a new turn. 231 offline tests pass. Reviewer and diagnosis findings (focus fallback, money amounts, same-turn carry-over, installments override, hidden pending operations) were fixed with regression tests. Catalog search now shows up to ten results (previously five). A six-turn live Qwen order evaluation passed after adding a current-message order-number guard; see OLLAMA_EVALUATION.md.

**Acceptance criteria**
- [x] Customer identity is established outside model-controlled fields and clearly labeled as simulated.
- [x] Foreign order access is blocked without leaking order existence or personal data.
- [x] Historical totals are preserved; missing tracking/estimate fields are not fabricated.
- [x] Estimates are labeled as estimates and never treated as actual receipt dates.
- [x] Tests cover accessible, inaccessible, nonexistent, and incomplete orders.

## P10 — Add payment options and supported freight calculations

Milestone: M3. Suggested labels: `feature`, `domain`. Dependencies: P03, P06, P07.

**Scope:** Implement installment rules only as documented, supported local freight, and explicit limitations for unsupported destinations/combined payment/special quotations.

**Acceptance criteria**
- [x] Installment count, minimum amount, rounding, quantity, and payment-method compatibility are tested.
- [x] Freight boundary tests include below, exactly, and above BRL 500.
- [x] Delivery-region membership and freight subtotal basis are documented, not inferred by the model.
- [x] No exact external freight quote or calendar delivery date is fabricated.
- [x] Ambiguous/unsupported conditions return the agreed confirmation/unavailable states.

Implemented on `feature/payment-freight`: §3.1 installment bands with cent-remainder rounding and maximum-count reporting, local Campo Grande/MS freight with BRL 500 boundary confirmation, region confirmation for other destinations, prompt examples, and tests. Code, security, and bug-diagnosis reviews were run and confirmed findings fixed (failed quotes reported before asking the destination, availability before region, payment facts carried into shipping, postal code contradicting the assumed state, once-per-response 2–3 installment note). Quotes also reuse and announce quantity and payment facts from the last successful, available quote of the same selected product; cancel, a new search, or another quote outcome forgets it. 388 offline tests pass.

## P11 — Add return assessment and missing-fact workflows

Milestone: M3. Suggested labels: `feature`, `domain`. Dependencies: P03, P07, P09.

**Scope:** Implement supported withdrawal, defect, and preference assessments, preserving distinct policy processes and source references.

**Acceptance criteria**
- [x] Required facts vary with the request; general questions do not demand an order unnecessarily.
- [x] Actual receipt, purchase channel, condition, and exclusions remain unknown until supplied or verified.
- [x] Date-boundary tests use an injected clock; estimates cannot substitute for receipt.
- [x] Customer declarations are labeled as such and do not authorize a transaction.
- [x] Ambiguous conditions request confirmation; no refund/cancellation action is claimed.

Implemented on `feature/return-assessment`: deterministic withdrawal, defect, and preference assessments in `returns.py`, per-reason required facts, order-record checks, provenance-labeled conditions, prompt examples, and 32 tests. Code, security, and bug-diagnosis reviews were run and their confirmed findings fixed (pending operations kept on clarification fallback, facts not carried across orders, stricter receipt-date and order-number filters, date expressions excluded from order numbers, no exception from carried facts, receipt before order date under review, DD/MM/YYYY receipt dates). 310 offline tests pass; live Qwen return and assignment sequences passed.

## P12 — Add grounded policy explanations and service fallbacks

Milestone: M3. Suggested labels: `feature`, `evaluation`. Dependencies: P03, P08, P10, P11.

**Scope:** Enable controller-selected general-policy prose, section references, out-of-scope redirection, small talk, and complaint acknowledgment. Keep critical data blocks in Python.

Minimal slice implemented on `feature/policy-answers`: separate policy call with section validation, `covered` flag, contact-conflict guard, fixed out-of-scope/small-talk/complaint templates, extraction examples for these routes, and catalog fallbacks for observed category/budget extraction errors. Code, security, and bug-diagnosis reviews were run and their confirmed findings fixed (budget formats, invented search terms, uncovered answers, obfuscated contacts, unsupported numbers and action claims, answer size, question provenance, history summary). 278 offline tests pass; a twelve-message live Qwen policy/service sequence, the assignment catalog examples, and the existing catalog and order sequences passed. Return-related questions still depend on P11. Published as PR #29; issue #20 remains open for the remaining criteria.

**Acceptance criteria**
- [x] Policy-reference validation exists, with explicit acknowledgment that it does not prove semantic correctness.
- [x] Individual policy decisions route to Python; free-form policy prose cannot bypass required assessment.
- [x] Accessory requests and unrelated topics are redirected appropriately.
- [x] Complaints receive empathy and an honest next step without false registration or transfer claims.
- [x] Known policy ambiguities and provider failures have stable fallbacks.
- [x] Mixed requests preserve independent answers and focused clarification.

Completed on `feature/service-fallbacks`: separate accessory and unrelated-topic redirects chosen in Python, a single product line for unique name quotes, and documentation of the remaining criteria (section validation without semantic proof, individual cases routed to Python assessments, complaint template, stable fallbacks, independent answers in mixed requests).

## P13 — Evaluate the complete agent and extend CI

Inputs recorded in `docs/OLLAMA_EVALUATION.md` (observed misinterpretations and open gaps).

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
- [ ] README discloses Codex and Claude Code usage for requirements analysis, planning, and any subsequent implementation/testing assistance actually used.
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
