# Ollama integration evaluation

Local verification on 2026-11-03 UTC (2026-11-02 in the developer timezone).
Provider: Windows-hosted Ollama accessed from WSL. Model: `qwen2.5:3b`.
Configuration: temperature 0, context 16384, generation limit 2048, socket timeout 120 seconds. No alternate model comparison or production reliability claim.

## Source review

`providers/store_manual.txt` contains the text extracted from all eight pages of the supplied manual, version 2.1, June 2025. Extraction decoded the embedded Unicode maps and text streams using Python's standard library. Page boundaries are retained as blank lines; table cells are flattened in source text order. The extracted sections were read and compared with the policy decisions already recorded in ARCHITECTURE.md, including installment bands, freight equality, and conflicting contacts. This is a textual review, not independent legal verification. The PDF remains external.

Source PDF SHA-256: `b7527f96896929f4ba929de117651c6717e25b7a3b92b34bc54d5ba32f6156f7`.

## Observed failures and adjustments

An initial real CLI query returned catalog results, but the follow-up produced a clarification envelope without an existing pending operation. Full-turn schema is now enforced when pending state is empty. Another attempt replayed a prior search; messages now place actual conversation history before the current reference context and current user message.

The model repeatedly omitted quantity in a price request, including “uma unidade” and “1 unidade”, despite valid schema output. Python safely requested quantity instead of calculating an assumed basket amount. Full-turn intent schemas now require explicit fields with null for unknown values; clarification schemas remain sparse to preserve update allowlists. These are observed model interpretation failures, not transport failures.

Live evaluations are opt-in with `python -m evals.ollama --url URL`; they do not run in CI. The small three-turn smoke set does not cover the later full evaluation milestone.

## Recorded three-turn smoke result

With explicit nullable fields required for full turns, a run completed the search in 1.78 seconds and the second-product PIX quote in 2.34 seconds. The quantity-correction case returned success in 3.09 seconds but failed the expected product/quantity assertion. This is a semantic failure despite a successful operation result. Earlier runs omitted quantity and safely requested clarification. One run failed at the provider boundary before any operation; a subsequent isolated call accepted the same schema. No reliability percentage is inferred from these development runs.

The model is usable for initial catalog integration, but corrections remain an observed limitation requiring further evaluation. A successful lookup and follow-up do not establish full conversational readiness.

The final rerun after strengthening correction instructions timed out on the first case after 120.05 seconds, producing a sanitized provider error and no executed operation. The latest prompt revision therefore has not passed the complete live smoke sequence. Live acceptance remains pending; no claim of a successful final run is made.

## Verification after restarting the server

On 2026-11-03 the server responded normally. Search passed in 12.99 seconds after startup, and the second-product PIX quote passed in 3.24 seconds. The quantity correction failed because the model reused ordinal 2 after the displayed list had been replaced by a single item. The adapter now constrains ordinal values to current displayed positions, with an offline regression checking schema isolation between requests.

A synthetic diagnostic then confirmed the corrected ordinal and quantity, but exposed an invented `installments=1` for PIX. Python correctly requested corrected payment conditions. After an explicit prompt instruction about null installment counts for PIX, the final run passed search (1.82 seconds) and the initial quote (3.15 seconds), but classified the quantity correction as `product_search` (2.90 seconds), failing the expected payment continuation. The transport is working; the final smoke sequence still fails semantic acceptance. No alternate model has been evaluated. The evaluator now additionally checks the PIX method and expected amounts of BRL 806.55 / 1613.10.

## Official prompt and Gemma comparison

On 2026-11-03 the user proposed an official persona/context prompt and requested a `gemma3:4b` comparison. The versioned source is `providers/prompts/extraction.md` (v1). It consolidates the earlier inline instructions and final reminders into one file, loaded after the full manual. It preserves extraction-only envelopes: free-text policy answers remain a separate P12 route. The user's proposed policy summary was adjusted to retain the approved installment ambiguity, city-specific local freight boundary, and unknown receipt facts. No new `answer` field or direct policy-response capability was added.

An initial Gemma run returned `query="violões Yamaha"`, which produced no matches under literal substring search. The prompt was clarified using a different brand/category example to explain that product category and brand/model terms belong in separate fields. Both models were then run sequentially with this same final prompt and the same three-turn script, schema, manual, and settings.

Prompt SHA-256: `03584f62e3a89155d0569d1ef1990bb36336f04d94793c33bbf981c1eb5b10ff`.

| Model | Search | Second-product PIX quote | Quantity correction |
| --- | --- | --- | --- |
| gemma3:4b | Passed, 10.27 s | Failed: needs_information, 2.77 s | Not executed: fail-fast evaluation |
| qwen2.5:3b | Passed, 15.65 s | Failed: needs_information, 2.26 s | Not executed: fail-fast evaluation |

These single runs include possible model loading and cache effects and are not a latency benchmark. They show no basis to prefer Gemma for this flow. The complete smoke sequence remains unpassed; the default model is unchanged pending further work on extraction/context. These cases have guided prompt development and are development smoke tests, not an independent held-out quality evaluation. All 207 offline tests passed after the prompt-loading refactor.

After the comparison, three user-requested contextual-reference examples were added to the official prompt (ordinal payment, ordinal quantity correction, selected shipping). The payment enum is lowercase `pix`; missing quantities/payment/destination facts remain unknown. The comparison above predates these examples and does not measure this prompt revision.

## Evaluation with contextual-reference examples

On 2026-11-03 both models were evaluated sequentially with the three added examples and unchanged transport settings, manual, and evaluator. Prompt SHA-256: `d930ad09adde35cdc93705bf6a0fe2e233870bb7ec1a0125bceb557ae3140867`. An earlier process session could not be recovered; no result is attributed to that attempt. The recorded rerun produced:

| Model | Search | Second-product PIX quote | Quantity correction |
| --- | --- | --- | --- |
| qwen2.5:3b | Passed, 15.48 s | Passed, 3.03 s | Passed, 1.92 s |
| gemma3:4b | Passed, 19.45 s | Failed, 2.59 s: quoted Yamaha C40 instead of Yamaha C70 | Not executed: fail-fast evaluation |

Qwen preserved Yamaha C70 Nylon Natural, quantity 1 then 2, PIX, and expected totals BRL 806.55 then BRL 1613.10. Gemma returned a successful payment operation for the wrong product, showing why schema validity and operation success are insufficient for semantic acceptance. The existing Qwen default is retained based on this limited successful development sequence. These are single development runs, not a representative accuracy estimate or a controlled speed benchmark; the smoke inputs have informed prompt revisions. Broader independent evaluation remains P13 work.

## Review corrections

Code and security review identified that interrupted chunked HTTP bodies and deeply nested response JSON could escape the provider error boundary and terminate the CLI. The adapter now converts `HTTPException` and `RecursionError` into the same sanitized `ProviderError`. Offline regressions exercise a real `HTTPResponse` with a truncated chunked body and a deeply nested 40 KB JSON envelope. All 209 deterministic tests and Ruff lint/format checks passed after the fix. No prompt or business-rule changes were made by this correction; the live evaluation above was not repeated.

## Order lookup evaluation (P09)

On 2026-11-03, `qwen2.5:3b` was run with unchanged transport settings against the bundled demonstration data, simulated customer 3, and the prompt including the two new `order_status` examples. Sequence: own order 1; "E o rastreio dele?"; foreign order 9; "Quero consultar meu pedido"; "É o número 19"; a Yamaha catalog search.

The first run passed five of six turns. After the foreign-order turn, the model copied order number 9 from history into "Quero consultar meu pedido", producing `not_found` instead of a request for the number. The extracted schema was valid; the error was semantic. The controller now discards an extracted `order_id` whose digits do not appear in the current message. The rerun passed all six turns: two successful own-order lookups (the second reusing the order in focus), a nonrevealing `not_found`, `needs_information`, a pending-update success for order 19, and a catalog search. The original three-turn catalog smoke sequence also passed again. These are single development runs informed by the observed failure, not an independent accuracy estimate.

## Quote clarification follow-up

During manual testing on 2026-11-03, "Quero 1 unidade do Yamaha C70" correctly asked for the payment method, but answering "PIX" then asked for the quantity again. Raw `qwen2.5:3b` output showed a new `payment_options` turn for the selected product with quantity omitted, instead of a pending update, so the pending quote and its declared quantity were replaced. The controller now carries declared facts into a new quote for the same pending product (see CONTRACT.md). Three live sequences ("PIX", "pix", "no PIX", with and without a prior search) then completed the quote in one step. 224 offline tests pass.

## Policy and service messages (P12 minimal slice)

On 2026-11-03, `qwen2.5:3b` was run without a simulated customer on twelve messages: greeting, address, hours, payment methods, defect exchange, phone number, guitar strings, an unrelated geography question, a delay complaint, a regret-return question, a mixed price-plus-hours message, and thanks. The first run misrouted four messages: payment methods as `payment_options`, the geography question as `policy_question` (the policy call answered it, citing §1), the complaint as `order_status`, and thanks as `product_search`. Extraction examples were added, and the policy schema gained a `covered` flag that Python maps to the out-of-scope template. A second run misread the greeting as thanks and quoted the Takamine GD20 under the wrong category; a greeting example and a name-only catalog retry were added.

The assignment's catalog examples then exposed two further extraction errors. "Violões até R$1000" produced `query: "viola"` with category `Violões`, and a following price question inherited the `R$ 1000` budget from history. Python now retries by category when the query shares the category stem and drops budgets absent from the current message. The final run routed all twelve messages as intended; the phone question returned the contact-conflict message, the regret return reported the unavailable P11 operation, and both assignment catalog examples succeeded. The catalog and order sequences above passed again. Policy prose was read manually: answers matched the manual sections cited, though the payment answer did not mention the installment bands. These single development runs informed the fixes and are not an independent accuracy estimate.

After code, security, and diagnosis reviews, the policy guards were tightened (contact obfuscation, manual-only numbers, executed-action claims, 1,000-character limit, current-message question). The first rerun exposed two regressions: the phone question returned `covered=false` (out-of-scope template), and the mixed price-plus-hours message lost its policy answer because the full message was sent. Contact requests are now answered deterministically, and the model-isolated question is used when it appears literally in the current message. The final rerun passed all twelve messages, both assignment catalog examples, and the catalog and order sequences.

## Return assessments (P11)

On 2026-11-03, `qwen2.5:3b` with simulated customer 3 handled a six-message return sequence: the assignment regret example, purchase channel and receipt date, product condition, a general defect-policy question, a defect case for order 1, and a preference exchange. Extraction routed each message as intended, the general question stayed a policy answer, and order 1 (from 2025) was reported outside the 30-day defect window with the manufacturer-warranty note. After reviews, a rerun showed that the model does not know the current date: it turned "recebi dia 1" into `today`, which the Python receipt filter discarded, and it then copied `01/11/2026` literally. Python now accepts `DD/MM/YYYY` receipt dates, and the clarification prompt shows that format; the rerun completed the withdrawal and defect cases.

## Store address (address fix)

Checking the four assignment examples exposed that "Qual o endereço da loja?" was extracted correctly as `policy_question` but the policy call returned `covered=false`, so the out-of-scope template was shown; "Onde fica a loja?" was answered correctly. The fixed §1.2 text is now a fallback only for whole-question store-address requests. In the final live run the model answered the address itself, so the fallback was not exercised live; it is covered offline.

## Installments and local freight (P10)

Live runs covered a Takamine GD20 price, 10 credit installments (R$ 219,90 each), local free freight with PIX (subtotal R$ 2.089,05), Dourados/MS (region confirmation), a follow-up "E qual o frete dele…" reusing the completed PIX quote, and a reset after `/cancelar`. Without history, three freight phrasings were extracted correctly as `shipping_quote` in two runs each; the model also filled `state: "MS"` when only "Campo Grande" was typed.

## Service messages (P12 completion)

An eight-message run (greeting, strings, case for a guitar, a 2002 World Cup question, a PIX quote, a delay complaint, Saturday hours plus a Yamaha C40 price, thanks) produced the intended routes and templates; "violão de 7 cordas" became a product search rather than an accessory redirect.

## Observed misinterpretations to evaluate (P13 input)

These single development runs are not accuracy estimates. Python guards prevented wrong facts in each case, but the customer received an incomplete or misrouted answer:

- With conversation history, a freight request ("Quero o Yamaha C40, uma unidade no boleto, qual o frete para Campo Grande?") was extracted as `payment_options`, so no freight was quoted; the same message without history was extracted correctly.
- "Quero o Violão Inexistente XYZ, qual o frete?" was routed to `out_of_scope` instead of a quote that reports no match.
- "Mostre violões Yamaha no cartão" omitted `payment_method: credit`.
- "Posso trocar por e-mail? Qual o prazo de troca por defeito?" was routed to an individual defect `return_assessment`, which asked for an order number.
- "O Yamaha C40 tem estoque? E vai chover amanhã?" dropped the product search and returned only the general redirect.
- In an address-plus-hours answer, the policy model cited only §1.2, not §2.
- Relative receipt dates without month and year cannot be resolved by the model, which has no current date.

## List references and PIX evidence

On 2026-11-03, `qwen2.5:3b` was compared with and without a new-product example on four sequences, three runs each. Without it, "adicione uma unidade do Crafter HT-100…" after a C40 PIX quote also requoted the C40 in all three runs; with it, only the Crafter was quoted, but the model copied `pix` in all three runs, even after a prompt rule against it. Prompt guidance therefore did not suffice, and Python now requires evidence for PIX, the only method that changes a price.

A final single run of three sequences gave the expected results for the Crafter follow-up (asks payment, then boleto), "E se forem 2 unidades?" (PIX reused with a notice), and ordinal quotes. Two gaps remain: "e em 10 vezes no crédito?" reported a maximum of 6x instead of the requested count, consistent with quantity 1 though the raw output was not captured, and "não quero pix, quanto fica?" gave no PIX discount but stayed on credit without asking. These are small development samples, not accuracy estimates.

## Consolidated evaluation and review (P13)

The [complete-agent evaluation](AGENT_EVALUATION.md) preserves the initial
2026-11-03 findings (27/29 automated passes and an additional warranty grounding
failure), the corrections, and subsequent verification. The latest run passed
29/29 automated checks and all seven marked manual reviews. One earlier reviewed
run had a sanitized provider error; its underlying cause remains unverified.

The controller now retains quantity on recognized payment-only follow-ups and
requires evidence for non-PIX methods too. Warranty-only policy answers use a
fixed reviewed summary after validation. The evaluator matches overlapping
expectations independently of response order. At that stage, all 489 offline tests and Ruff
checks passed. No prompts, dependencies, or infrastructure changed. These small
development-informed runs are not a general accuracy estimate; the report records
remaining limitations and links five real conversation transcripts.
