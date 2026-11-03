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
