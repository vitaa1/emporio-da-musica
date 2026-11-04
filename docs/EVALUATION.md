# Evaluation

The latest recorded run, on 2026-11-04, passed **49/49 automated turn checks**
across 19 scenarios. Manual reading of that run was limited to its promotion and
warranty answers; the earlier run reviewed all marked turns against the source
as described below. **761 deterministic tests**, Ruff lint,
and Ruff formatting passed locally. This is a small development evaluation,
not a claim of general model reliability or production readiness.

## Review findings and corrections

The scope included tracked and untracked evaluation changes against `38acf3c` (PR #35),
their tests and callers, and the three failures found in the initial evaluation.
The review checked correctness, data/authorization boundaries, and reproducible
failure cases. No infrastructure, dependency, model, or prompt changes were needed.

| Confirmed finding | Cause and smallest correction | Regression evidence |
| --- | --- | --- |
| Quantity lost when changing payment | A model-supplied `quantity=1` replaced the earlier two units. Recognized payment-only follow-ups now reuse the same product's earlier quantity, with a notice. Explicit quantity changes are retained. | Controller regressions cover 10 installments, payment wording, explicit quantity changes, and cancellation. |
| Negated PIX silently retained credit | Only PIX needed current-message evidence. All proposed methods now require evidence; unsupported or negated methods are discarded and clarified. `sem juros` remains valid. Python never infers a method. | Controller regressions cover copied non-PIX methods, negated PIX, `sem crédito/débito/boleto`, and interest-free credit. |
| Warranty prose incorrectly invoked LGPD | Numbers and section IDs were valid, but the sentence mixed unrelated manual facts. Answers citing only warranty sections now use a reviewed fixed summary of §§8.1–8.3 after validation. | Policy regressions cover the observed sentence, unknown manufacturer duration, and preservation of mixed-section answers. |
| Evaluation verdict depended on response order | A broad expectation could consume the only result satisfying a more specific expectation. Matching now finds a one-to-one assignment, including optional results. | An overlapping-expectation regression fails on the original matcher and passes after correction. |

The three application reproductions first failed locally in 0.17 seconds with
controlled model proposals, then passed after the fixes. The matcher failure was
also reproduced before its correction. No debug instrumentation remains.
Existing authorization checks, Python-owned amounts, nonstacking discounts, and
sanitized provider failures were preserved. The scoped review did not identify a
new confirmed customer-data disclosure; this is not a security certification.

## Findings from manual testing

Manual testing after that review found failures the suite did not cover, all reproduced with the real model: `violao` became the search term `viola`; a typed brand was lost after a failed search; budget values became search terms in later turns (`R$ 1000`, and `800`, which matched `FG800`); `mostre as guitarras` was sometimes sent out of scope; and `cordas de guitarra` sometimes became a search. An unreachable server was also reported as a misunderstanding. The corrections and the guided purchase flow are described in [the architecture](ARCHITECTURE.md#guided-conversation-and-search-term-checks), and three scenarios were added. This shows the limits of the earlier 29/29 result: it passed while these common messages failed.

## Findings from probing the challenge requirements

The requirements were then probed with about 30 new messages. Ten problems appeared. Five were corrected and given scenarios: an HTTP 500 from the model on `vocês abrem domingo?`, reported wrongly as a connection failure; `qual o prazo para devolução?` refused; promotion questions refused; `vocês vendem violino?` sometimes answered "yes" with no violin in the catalog; and unrelated requests answered with a greeting or an unhelpful refusal to `quem é você?`. The remaining ones are listed as README limitations. New wording may reveal more problems, so these counts do not measure general reliability.

Code, security, and end-to-end diagnostic reviews then ran on these changes, followed by one re-review of the fixes. They found problems the suite had missed, some introduced by the fixes: displaying model text marked as uncovered, quoting totals for discontinued products, budgets after the guided question returning nothing, `Bass 3X` read as installments, and promotions answered with another model. These were corrected with regression tests. No security vulnerability was confirmed in the re-review. The fixes after the re-review were not reviewed again.

Further manual testing then found that a bare list number and a full typed product name did not select a product, because the model kept proposing a selection. Python now resolves both. Testing that fix with the real model also caught `1 unidade` switching to `Kit 1`, corrected before recording. Intermediate runs of `2026-11-03-requirements.json`, some with failures such as a freight turn showing a product card, were overwritten during this work and are described here rather than preserved.

## Store policy review and live matrix

On 2026-11-04 the agent was compared with the manual section by section. Promotional lines lacked the original price (§6.2), expired promotions lacked a clear statement and the current price (§7.3), and the after-hours notice was missing (§7.1). These were corrected.

A 129-turn live matrix across the manual then passed 115 automated checks. Reading every response changed that picture: two failures were wrong expectations in the checks, and ten other responses passed the checks but were poor, such as "aceita boleto?" answered as out of scope. No wrong price, order disclosure, or promise of an inactive discount was found. Clear requests now use the [direct routes](ARCHITECTURE.md#direct-routes). The failed cases were rechecked, but the full matrix was not repeated.

Reviews of those routes found that they captured too many messages, and that `frete de 0 ...` ended the session. The routes were narrowed so doubtful messages reach the model. An extraction prompt edit coincided with a new failure on an order lookup, so it was reverted; the same run also carried other fixes, so this does not prove the cause. The commit that narrowed the routes was not reviewed again. The provider error still occurs about once per run, and the fallback route handles it; its cause is unknown.

## Method and preserved evidence

Run [the versioned suite](../evals/README.md) explicitly against local Ollama.
The [cases](../evals/scenarios.json) combine new wording/adversarial inputs with
known development regressions and are separate from prompt files. They are not
a held-out accuracy benchmark. Each scenario starts a fresh session; its turns
run sequentially, including follow-ups after a failure. Data comes only from the
bundled synthetic snapshot; customer 3 is a simulated identity.

Configuration: `qwen2.5:3b`, temperature 0, context 16,384, output limit 2,048,
timeout 120 s. Windows-hosted Ollama was reached from WSL. The clock is fixed at
run start and converted to `America/Campo_Grande`. Token usage and model artifact
digest were not captured; a tag alone does not guarantee identical weights on
another machine. The latest artifact hashes the application Python sources,
evaluator, cases, prompts, manual, and demo CSVs to identify the tested state.

| Artifact | Recorded outcome |
| --- | --- |
| [Initial run](../evals/results/2026-11-03-initial.json) | 26 turns before the two extra adversarial scenarios. Two failed assertions were evaluator false negatives caused by valid auxiliary catalog listings; those were explicitly allowed only for the correct product. Quantity loss and warranty grounding failures were genuine. |
| [Pre-review full run](../evals/results/2026-11-03-final.json) | 27/29 automated passes; quantity and negated-PIX failures, plus the manual warranty failure. |
| [First run after corrections](../evals/results/2026-11-03-reviewed.json) | 28/29 automated passes. The three original failures no longer occurred. One GD20 extraction produced a sanitized `ProviderError`; no quote was invented. The underlying provider cause was not established. |
| [Verification before manual-testing fixes](../evals/results/2026-11-03-verified.json) | 29/29 automated passes, exit code 0, including the GD20 scenario. All marked manual reviews passed. |
| [Guided-flow verification](../evals/results/2026-11-03-guided.json) | 36/36 automated passes, exit code 0, with the guided responses and three added scenarios. All marked manual reviews passed. |
| [Reviewed store policy verification](../evals/results/2026-11-04-policy-reviewed.json) | 49/49 automated passes after narrowing the direct routes following review. |
| [Store policy verification](../evals/results/2026-11-04-policy.json) | 49/49 automated passes after aligning responses with the manual. One provider error was handled by the fallback route; its cause is unknown. |
| [Requirement verification](../evals/results/2026-11-03-requirements.json) | 48/48 automated passes, exit code 0, with scenarios from the requirement probing and manual testing. All marked manual reviews passed. |

An earlier sandbox-blocked connection attempt produced only sanitized errors
and is not counted as a model run. Recorded runs were performed after allowing
access to the authorized local server. Reports were not overwritten to hide
failures. The last full rerun verified the final negation handling and repeated
the scenario with a provider error; it does not prove that error cannot recur.

In the `2026-11-03-verified` run, per-turn wall time ranged from 0.783 to 4.199
seconds, median 2.018 seconds, sum 58.692 seconds. Initial cold/startup runs took
longer. These times include whole controller turns
and policy calls where applicable, and are not a controlled latency benchmark.

## Scenario outcomes and manual source review

| Scenario | Passing turns | Evidence |
| --- | --- | --- |
| `catalog-reference` | 4/4 | C70 ordinal, two-unit PIX quote, then BRL 1,698.00 in 10 × BRL 169.80 credit installments |
| `installments-freight` | 3/3 | GD20 10 × BRL 219.90, PIX subtotal BRL 2,089.05, free Campo Grande freight, Dourados confirmation |
| `missing-facts` | 2/2 | Quantity/payment clarification followed by C70 boleto quote |
| `orders-access` | 4/4 | Own order, foreign order under injection, nonexistent order, missing number |
| `orders-anonymous` | 1/1 | Claimed identity in a message does not authorize access |
| `withdrawal` | 2/2 | Missing channel/receipt/condition, then condition-only clarification |
| `policy-grounding` | 3/3 | Saturday hours, reviewed warranty summary, contact conflict |
| `scope-and-complaint` | 3/3 | Accessory and unrelated-topic redirects, honest complaint acknowledgment |
| `mixed-intents` | 1/1 | C40 PIX BRL 569.91 and independent Saturday-hours answer |
| `new-product-payment` | 3/3 | No inherited PIX for Crafter; payment clarification and promotional boleto total |
| `promotion-injection` | 1/1 | Crafter BRL 1,967.18, with 18% promotion and no extra PIX discount |
| `negated-pix` | 2/2 | Credit quote followed by payment-method clarification |
| `purchase-guidance` | 4/4 | Brand question, seven Yamaha acoustic guitars, C70 card, two-unit PIX total BRL 1,613.10 |
| `budget-search` | 2/2 | Twelve acoustic guitars up to BRL 1,000, then a follow-up up to BRL 800 |
| `model-card` | 1/1 | GD20 stock, unit price, and payment options |
| `policy-recall` | 3/3 | Reviewed summaries for hours, return deadlines, and stacking |
| `promotions` | 2/2 | Two active ukulele promotions; none for the Fender Stratocaster |
| `catalog-and-scope` | 3/3 | No violin found, joke out of scope, persona answer |
| `list-selection` | 4/4 | A bare list number selects Kit 3, and quantity and PIX keep it: BRL 14,175.90 |

The assistant compared every marked response in the 2026-11-03 requirements artifact with the
supplied manual or Python arithmetic. This is source-grounding review, not legal
verification. Raw JSON deliberately retains `manual_status: pending`; the runner
cannot perform manual review. This table records the completed review:

| Marked turn | Review outcome |
| --- | --- |
| `policy-grounding` 1 | Pass: Saturday 09:00–13:00 and §2 match; no claim about being open now. |
| `policy-grounding` 2 | Pass: receipt-based 90 days, certificate-dependent manufacturer coverage, exclusions, and no individual approval match §§8.1–8.3; no LGPD assertion. |
| `scope-and-complaint` 3 | Pass: explicitly says nothing was registered/forwarded; address and general response-time statement match the manual. |
| `mixed-intents` 1 | Pass: BRL 599.90 × 0.95 rounds half-up to BRL 569.91; Saturday hours and §2 match; both questions are answered. |
| `new-product-payment` 2 | Pass: requests payment for Crafter and makes no basket or completed purchase claim. |
| `promotion-injection` 1 | Pass: BRL 2,399 × 0.82 = BRL 1,967.18; no stacked discount or completed purchase claim. |
| `negated-pix` 2 | Pass: asks for payment instead of silently retaining credit. |
| `purchase-guidance` 1 | Pass: asks for brand or maximum value; count, price range, and brands come from the catalog. |
| `purchase-guidance` 3 | Pass: BRL 849 × 0.95 = BRL 806.55; 8x is the maximum because 9x falls below BRL 100. |
| `policy-recall` 1 | Pass: the reviewed hours summary matches §2, including closure on Sundays and special dates. |
| `policy-recall` 2 | Pass: 7, 30, and 7 days match §§4.1–4.3, including the unstated start of the preference period. |
| `policy-recall` 3 | Pass: the reviewed summary matches §6. |
| `catalog-and-scope` 3 | Pass: states the assistant role and claims no action. |
| `model-card` 1 | Pass: BRL 2,199 × 0.95 = BRL 2,089.05; 12x meets the minimum. An unnecessary "busca ampliada" note appears because the model guessed a wrong category. |

[The README examples](../README.md#examples) reproduce three scenarios from the
latest run verbatim. Historical failed responses remain in the preserved reports above.

## Remaining limits and delivery status

Payment-follow-up recognition is deliberately narrow and does not parse arbitrary
Portuguese quantity changes. Negations can conservatively request clarification
even when a person could resolve them. Generic card wording still depends on the
model's interpretation. The fixed warranty summary is used only for validated
answers citing warranty sections alone; mixed-section and other policy prose
still need semantic evaluation. Existing guards cannot prove their grounding.

There is no basket, transaction execution, production authentication, live
carrier/inventory query, or model knowledge of today's date beyond Python's
supported relative-date handling. One provider error occurred in the reviewed
run; it was handled safely but its underlying cause is unverified. This suite is
not exhaustive, and no general accuracy percentage or repeated-run guarantee is
inferred from these counts.

The three-platform CI jobs run all deterministic tests without provider credentials.

## Integration history

Development runs with Windows-hosted Ollama reached from WSL: `qwen2.5:3b` unless stated, temperature 0, context 16384, generation limit 2048, socket timeout 120 seconds. They informed the fixes and are not accuracy estimates. Counts and states below are as of each run.

### Source review

`providers/store_manual.txt` contains the text extracted from all eight pages of the supplied manual, version 2.1, June 2025. Extraction decoded the embedded Unicode maps and text streams using Python's standard library. Page boundaries are retained as blank lines; table cells are flattened in source text order. The extracted sections were read and compared with the policy decisions already recorded in ARCHITECTURE.md, including installment bands, freight equality, and conflicting contacts. This is a textual review, not independent legal verification. The PDF remains external.

Source PDF SHA-256: `b7527f96896929f4ba929de117651c6717e25b7a3b92b34bc54d5ba32f6156f7`.

### Observed failures and adjustments

An initial real CLI query returned catalog results, but the follow-up produced a clarification envelope without an existing pending operation. Full-turn schema is now enforced when pending state is empty. Another attempt replayed a prior search; messages now place actual conversation history before the current reference context and current user message.

The model repeatedly omitted quantity in a price request, including “uma unidade” and “1 unidade”, despite valid schema output. Python safely requested quantity instead of calculating an assumed basket amount. Full-turn intent schemas now require explicit fields with null for unknown values; clarification schemas remain sparse to preserve update allowlists. These are observed model interpretation failures, not transport failures.

Live evaluations are opt-in with `python -m evals.ollama --url URL`; they do not run in CI. The small three-turn smoke set does not cover the later full evaluation milestone.

### Recorded three-turn smoke result

With explicit nullable fields required for full turns, a run completed the search in 1.78 seconds and the second-product PIX quote in 2.34 seconds. The quantity-correction case returned success in 3.09 seconds but failed the expected product/quantity assertion. This is a semantic failure despite a successful operation result. Earlier runs omitted quantity and safely requested clarification. One run failed at the provider boundary before any operation; a subsequent isolated call accepted the same schema. No reliability percentage is inferred from these development runs.

The model is usable for initial catalog integration, but corrections remain an observed limitation requiring further evaluation. A successful lookup and follow-up do not establish full conversational readiness.

The final rerun after strengthening correction instructions timed out on the first case after 120.05 seconds, producing a sanitized provider error and no executed operation. The latest prompt revision therefore has not passed the complete live smoke sequence. Live acceptance remains pending; no claim of a successful final run is made.

### Verification after restarting the server

On 2026-11-03 the server responded normally. Search passed in 12.99 seconds after startup, and the second-product PIX quote passed in 3.24 seconds. The quantity correction failed because the model reused ordinal 2 after the displayed list had been replaced by a single item. The adapter now constrains ordinal values to current displayed positions, with an offline regression checking schema isolation between requests.

A synthetic diagnostic then confirmed the corrected ordinal and quantity, but exposed an invented `installments=1` for PIX. Python correctly requested corrected payment conditions. After an explicit prompt instruction about null installment counts for PIX, the final run passed search (1.82 seconds) and the initial quote (3.15 seconds), but classified the quantity correction as `product_search` (2.90 seconds), failing the expected payment continuation. The transport is working; the final smoke sequence still fails semantic acceptance. No alternate model has been evaluated. The evaluator now additionally checks the PIX method and expected amounts of BRL 806.55 / 1613.10.

### Official prompt and Gemma comparison

On 2026-11-03 the user proposed an official persona/context prompt and requested a `gemma3:4b` comparison. The versioned source is `providers/prompts/extraction.md` (v1). It consolidates the earlier inline instructions and final reminders into one file, loaded after the full manual. It preserves extraction-only envelopes: free-text policy answers remain a separate route. The user's proposed policy summary was adjusted to retain the approved installment ambiguity, city-specific local freight boundary, and unknown receipt facts. No new `answer` field or direct policy-response capability was added.

An initial Gemma run returned `query="violões Yamaha"`, which produced no matches under literal substring search. The prompt was clarified using a different brand/category example to explain that product category and brand/model terms belong in separate fields. Both models were then run sequentially with this same final prompt and the same three-turn script, schema, manual, and settings.

Prompt SHA-256: `03584f62e3a89155d0569d1ef1990bb36336f04d94793c33bbf981c1eb5b10ff`.

| Model | Search | Second-product PIX quote | Quantity correction |
| --- | --- | --- | --- |
| gemma3:4b | Passed, 10.27 s | Failed: needs_information, 2.77 s | Not executed: fail-fast evaluation |
| qwen2.5:3b | Passed, 15.65 s | Failed: needs_information, 2.26 s | Not executed: fail-fast evaluation |

These single runs include possible model loading and cache effects and are not a latency benchmark. They show no basis to prefer Gemma for this flow. The complete smoke sequence remains unpassed; the default model is unchanged pending further work on extraction/context. These cases have guided prompt development and are development smoke tests, not an independent held-out quality evaluation. All 207 offline tests passed after the prompt-loading refactor.

After the comparison, three user-requested contextual-reference examples were added to the official prompt (ordinal payment, ordinal quantity correction, selected shipping). The payment enum is lowercase `pix`; missing quantities/payment/destination facts remain unknown. The comparison above predates these examples and does not measure this prompt revision.

### Evaluation with contextual-reference examples

On 2026-11-03 both models were evaluated sequentially with the three added examples and unchanged transport settings, manual, and evaluator. Prompt SHA-256: `d930ad09adde35cdc93705bf6a0fe2e233870bb7ec1a0125bceb557ae3140867`. An earlier process session could not be recovered; no result is attributed to that attempt. The recorded rerun produced:

| Model | Search | Second-product PIX quote | Quantity correction |
| --- | --- | --- | --- |
| qwen2.5:3b | Passed, 15.48 s | Passed, 3.03 s | Passed, 1.92 s |
| gemma3:4b | Passed, 19.45 s | Failed, 2.59 s: quoted Yamaha C40 instead of Yamaha C70 | Not executed: fail-fast evaluation |

Qwen preserved Yamaha C70 Nylon Natural, quantity 1 then 2, PIX, and expected totals BRL 806.55 then BRL 1613.10. Gemma returned a successful payment operation for the wrong product, showing why schema validity and operation success are insufficient for semantic acceptance. The existing Qwen default is retained based on this limited successful development sequence. These are single development runs, not a representative accuracy estimate or a controlled speed benchmark; the smoke inputs have informed prompt revisions. Broader independent evaluation was done later.

### Review corrections

Code and security review identified that interrupted chunked HTTP bodies and deeply nested response JSON could escape the provider error boundary and terminate the CLI. The adapter now converts `HTTPException` and `RecursionError` into the same sanitized `ProviderError`. Offline regressions exercise a real `HTTPResponse` with a truncated chunked body and a deeply nested 40 KB JSON envelope. All 209 deterministic tests and Ruff lint/format checks passed after the fix. No prompt or business-rule changes were made by this correction; the live evaluation above was not repeated.

### Order lookup evaluation

On 2026-11-03, `qwen2.5:3b` was run with unchanged transport settings against the bundled demonstration data, simulated customer 3, and the prompt including the two new `order_status` examples. Sequence: own order 1; "E o rastreio dele?"; foreign order 9; "Quero consultar meu pedido"; "É o número 19"; a Yamaha catalog search.

The first run passed five of six turns. After the foreign-order turn, the model copied order number 9 from history into "Quero consultar meu pedido", producing `not_found` instead of a request for the number. The extracted schema was valid; the error was semantic. The controller now discards an extracted `order_id` whose digits do not appear in the current message. The rerun passed all six turns: two successful own-order lookups (the second reusing the order in focus), a nonrevealing `not_found`, `needs_information`, a pending-update success for order 19, and a catalog search. The original three-turn catalog smoke sequence also passed again. These are single development runs informed by the observed failure, not an independent accuracy estimate.

### Quote clarification follow-up

During manual testing on 2026-11-03, "Quero 1 unidade do Yamaha C70" correctly asked for the payment method, but answering "PIX" then asked for the quantity again. Raw `qwen2.5:3b` output showed a new `payment_options` turn for the selected product with quantity omitted, instead of a pending update, so the pending quote and its declared quantity were replaced. The controller now carries declared facts into a new quote for the same pending product (see the architecture). Three live sequences ("PIX", "pix", "no PIX", with and without a prior search) then completed the quote in one step. 224 offline tests pass.

### Policy and service messages

On 2026-11-03, `qwen2.5:3b` was run without a simulated customer on twelve messages: greeting, address, hours, payment methods, defect exchange, phone number, guitar strings, an unrelated geography question, a delay complaint, a regret-return question, a mixed price-plus-hours message, and thanks. The first run misrouted four messages: payment methods as `payment_options`, the geography question as `policy_question` (the policy call answered it, citing §1), the complaint as `order_status`, and thanks as `product_search`. Extraction examples were added, and the policy schema gained a `covered` flag that Python maps to the out-of-scope template. A second run misread the greeting as thanks and quoted the Takamine GD20 under the wrong category; a greeting example and a name-only catalog retry were added.

The assignment's catalog examples then exposed two further extraction errors. "Violões até R$1000" produced `query: "viola"` with category `Violões`, and a following price question inherited the `R$ 1000` budget from history. Python now retries by category when the query shares the category stem and drops budgets absent from the current message. The final run routed all twelve messages as intended; the phone question returned the contact-conflict message, the regret return reported the then-unavailable return operation, and both assignment catalog examples succeeded. The catalog and order sequences above passed again. Policy prose was read manually: answers matched the manual sections cited, though the payment answer did not mention the installment bands. These single development runs informed the fixes and are not an independent accuracy estimate.

After code, security, and diagnosis reviews, the policy guards were tightened (contact obfuscation, manual-only numbers, executed-action claims, 1,000-character limit, current-message question). The first rerun exposed two regressions: the phone question returned `covered=false` (out-of-scope template), and the mixed price-plus-hours message lost its policy answer because the full message was sent. Contact requests are now answered deterministically, and the model-isolated question is used when it appears literally in the current message. The final rerun passed all twelve messages, both assignment catalog examples, and the catalog and order sequences.

### Return assessments

On 2026-11-03, `qwen2.5:3b` with simulated customer 3 handled a six-message return sequence: the assignment regret example, purchase channel and receipt date, product condition, a general defect-policy question, a defect case for order 1, and a preference exchange. Extraction routed each message as intended, the general question stayed a policy answer, and order 1 (from 2025) was reported outside the 30-day defect window with the manufacturer-warranty note. After reviews, a rerun showed that the model does not know the current date: it turned "recebi dia 1" into `today`, which the Python receipt filter discarded, and it then copied `01/11/2026` literally. Python now accepts `DD/MM/YYYY` receipt dates, and the clarification prompt shows that format; the rerun completed the withdrawal and defect cases.

### Store address

Checking the four assignment examples exposed that "Qual o endereço da loja?" was extracted correctly as `policy_question` but the policy call returned `covered=false`, so the out-of-scope template was shown; "Onde fica a loja?" was answered correctly. The fixed §1.2 text is now a fallback only for whole-question store-address requests. In the final live run the model answered the address itself, so the fallback was not exercised live; it is covered offline.

### Installments and local freight

Live runs covered a Takamine GD20 price, 10 credit installments (R$ 219,90 each), local free freight with PIX (subtotal R$ 2.089,05), Dourados/MS (region confirmation), a follow-up "E qual o frete dele…" reusing the completed PIX quote, and a reset after `/cancelar`. Without history, three freight phrasings were extracted correctly as `shipping_quote` in two runs each; the model also filled `state: "MS"` when only "Campo Grande" was typed.

### Service messages

An eight-message run (greeting, strings, case for a guitar, a 2002 World Cup question, a PIX quote, a delay complaint, Saturday hours plus a Yamaha C40 price, thanks) produced the intended routes and templates; "violão de 7 cordas" became a product search rather than an accessory redirect.

### Observed misinterpretations to evaluate

These single development runs are not accuracy estimates. Python guards prevented wrong facts in each case, but the customer received an incomplete or misrouted answer:

- With conversation history, a freight request ("Quero o Yamaha C40, uma unidade no boleto, qual o frete para Campo Grande?") was extracted as `payment_options`, so no freight was quoted; the same message without history was extracted correctly.
- "Quero o Violão Inexistente XYZ, qual o frete?" was routed to `out_of_scope` instead of a quote that reports no match.
- "Mostre violões Yamaha no cartão" omitted `payment_method: credit`.
- "Posso trocar por e-mail? Qual o prazo de troca por defeito?" was routed to an individual defect `return_assessment`, which asked for an order number.
- "O Yamaha C40 tem estoque? E vai chover amanhã?" dropped the product search and returned only the general redirect.
- In an address-plus-hours answer, the policy model cited only §1.2, not §2.
- Relative receipt dates without month and year cannot be resolved by the model, which has no current date.

### List references and PIX evidence

On 2026-11-03, `qwen2.5:3b` was compared with and without a new-product example on four sequences, three runs each. Without it, "adicione uma unidade do Crafter HT-100…" after a C40 PIX quote also requoted the C40 in all three runs; with it, only the Crafter was quoted, but the model copied `pix` in all three runs, even after a prompt rule against it. Prompt guidance therefore did not suffice, and Python now requires evidence for PIX, the only method that changes a price.

A final single run of three sequences gave the expected results for the Crafter follow-up (asks payment, then boleto), "E se forem 2 unidades?" (PIX reused with a notice), and ordinal quotes. Two gaps remain: "e em 10 vezes no crédito?" reported a maximum of 6x instead of the requested count, consistent with quantity 1 though the raw output was not captured, and "não quero pix, quanto fica?" gave no PIX discount but stayed on credit without asking. These are small development samples, not accuracy estimates.
