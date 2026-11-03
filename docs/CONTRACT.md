# Agent–Controller Contract

Status: version 1 contracts implemented for issue #8. Pydantic schemas, date resolution, scoped pending updates, session construction, and the provider extraction boundary exist in code. Catalog search and nonstacking pricing are implemented in `catalog.py`. The offline catalog controller, CLI, and deterministic composer are implemented for issue #10. A local Ollama adapter is implemented for P08. Session-scoped order lookup is implemented for P09 (issue #12). General policy explanations and out-of-scope, small-talk, and complaint templates are implemented as a minimal P12 slice (issue #20). Return assessments are implemented in `returns.py` for P11 (issue #19). Credit installment bands and local freight quotes are implemented for P10 (issue #18).

## Implemented interfaces and limits

| Module | Implemented responsibility |
| --- | --- |
| `contracts/common.py` | Strict, extra-forbidden, frozen model configuration and bounded scalar types. |
| `contracts/intents.py` | Nine intent variants, complete-turn and clarification schemas, and sanitized JSON parsing. |
| `contracts/dates.py` | Injected aware clock, store date, and receipt-date resolution. |
| `contracts/results.py` | Discriminated operation results with operation-specific data and status consistency. |
| `contracts/session.py` | Startup identity validation, bounded session history, provenance, and pending-update allowlists. |
| `providers/base.py` | Provider protocol, minimal request context, and provider errors. |
| `providers/extraction.py` | Validated extraction with one schema-repair attempt; no operation dispatch. |
| `providers/ollama.py` | Local Ollama structured extraction, bounded transport, and reviewed manual context. |
| `providers/demo.py` | Offline command-based provider implementing the extraction protocol. |
| `controller.py` | Sequential catalog execution, actual-record references, scoped pending updates, and sanitized failure handling. |
| `composer.py` | Portuguese catalog prices, availability, limitations, and focused clarification templates. |
| `cli.py` | Bounded offline command-based demonstration using a fake provider. |

The public model-output entry point is `parse_proposal(raw_json, clock=...)`. It accepts only an `IntentTurn` or `ClarificationUpdate`, never session state or an operation result. Python integers and booleans are strict: `true`, `"1"`, and `1.0` are not quantities. Budgets accept nonnegative decimal strings with up to two fractional digits. Missing extracted fields remain `None`; in particular, quantity and availability filters are never inferred by schema defaults. Catalog inquiries may use quantity one for a unit-price question only with an explicit quote assumption; basket quantities must be obtained from the customer.

The implemented limits are five intents, 20 history messages, five pending operations, 4,000 characters per text field, and 32,000 UTF-8 bytes per provider response. Limits live in Python, not model output. Empty turns, unknown/extra fields (including nested fields), duplicate JSON keys, and malformed values are rejected. More than five intents raises `RequestTooBroadError`, which bypasses schema repair so the future controller can ask the customer to narrow the request. Other malformed outputs raise `ProposalError("Invalid model proposal")`, without echoing raw inputs. Do not log raw Pydantic `.errors()` payloads, which can contain input values despite sanitized string representations.

`received_at` accepts ISO dates or exactly `today`, `yesterday`, and `day_before_yesterday`; Python resolves these against the injected clock in `America/Campo_Grande`. Other relative/ambiguous expressions must be clarified rather than guessed. A receipt after the store's current date is rejected. The parsed value is a customer-declared date, not a verified receipt. `tzdata` is a runtime dependency to support Windows as well as platforms with a system timezone database. A naive clock is a configuration error, not a model repair opportunity.

A clarification uses this alternative envelope:

```json
{
  "pending_id": "controller-issued-id",
  "update": {
    "type": "shipping_quote",
    "payment_method": "pix"
  }
}
```

`PendingOperation.apply_update` checks the pending ID, unchanged intent type, and a nonempty set of explicitly supplied fields against its requested-field allowlist. Null remains unknown. `condition` and `destination` patches merge only supplied nested members, preserving previously declared facts; explicit null clears the object. Other supplied fields replace their prior declaration. The method returns validated declarations, remaining unfilled requested fields, and cleared record references; it does not mutate the old state or execute an operation. Required facts and product/order resolution are re-evaluated by the controller before executing dependent calculations. Top-level requested fields authorize their typed nested fields, never arbitrary session updates. Pending IDs are correlation identifiers, not authentication tokens.

Session history is held as a bounded tuple; appending evicts the oldest message. `create_session(snapshot, customer_id)` validates an optional startup-selected simulated identity and rejects unknown/noninteger IDs. Identity is not a provider request/output field and is frozen in the session object. `DeclaredFacts` and `RecordReferences` keep customer declarations and Python-resolved records separate. Selected product IDs must belong to the displayed list. These are internal Python state contracts. The offline controller now resolves ordinals against the actually displayed list, supports cancellation, and runs catalog operations sequentially. Order queries are authorized in Python against the startup identity: no identity yields `unauthorized` without reading orders; foreign and nonexistent IDs yield the same `not_found`/`ORDER_NOT_ACCESSIBLE` result; a missing ID yields `needs_information` unless a previous successful lookup set `selected_order_id`. Local Ollama conversation is implemented. Never deserialize an entire session from model output.

`IntentProvider.propose(ProviderRequest)` returns raw JSON. Requests contain message/history, displayed product names in order, pending-field hints, and a repair flag; they have no customer table, identity, authoritative price, or arbitrary session state field. The caller must minimize any personal data in message/history text. `extract_proposal` validates the response and permits one repair call with the same context and a generic flag. A second invalid response is an error. Provider adapters translate connection/timeouts into `ProviderError`; that error is propagated without schema repair. The versioned `providers/prompts/extraction.md` is the official extraction prompt; it introduces no free-text response fields. The Ollama adapter now implements local model calls with a 120-second socket timeout and no transport retries. A separate optional `PolicyProvider.explain(PolicyRequest)` receives only text from the current message and returns JSON validated as `covered`, `answer`, and known `policy_references`; `providers/policy.py` rejects malformed or oversized answers, contact details (`CONTACT_CONFLICT`, `requires_confirmation`), executed-action claims, and numbers absent from the manual; contact requests bypass the model (detected in the isolated question when the model supplies one literally present in the message, otherwise in the whole message, so a contact word elsewhere does not hide another policy question); when the policy model reports an explicit store-address question as uncovered or fails, the controller answers with fixed §1.2 text instead of the out-of-scope template or error (the small model sometimes reported “Qual o endereço da loja?” as uncovered). The fallback applies only when the entire question (the isolated question, or the whole message when none is isolated) is a store-address request (`qual o endereço [da loja/de vocês]`, `rua/localização/CEP da loja`, `onde fica a loja`, `onde vocês ficam`, `como chegar aí`, with an optional greeting or `por favor`), so mixed questions, delivery addresses, and order locations keep their normal outcome and a covered answer is never replaced. If the message asks for a contact but no policy result already carries the conflict notice (for example, the model isolated only another question), one notice is added; a fixed address fallback is omitted next to that notice, which already includes the address. Limitation: when the model does not isolate a question literally, a contact word anywhere in the message still yields only the conflict notice for that intent; uncovered questions become the out-of-scope template. The controller dispatches catalog operations only after extraction succeeds.

Results are Python-owned and discriminated by `operation`. Success requires the corresponding typed data and no missing fields; `needs_information` requires missing fields, no data, and a reason code. Other statuses require a reason code and cannot carry data or missing fields. IDs default to Python-generated UUIDs. Catalog/payment data carries explicit quantity, availability, list unit price, promotion, payment condition, final total, and assumptions; order data omits customer details and preserves recorded total plus optional tracking/estimate. Return data contains the reason, an overall assessment, and condition states with provenance, never a refund action. Service results select only operation-appropriate template keys. Out-of-scope results use `accessory_redirect` when the model's topic (or, without a topic, a single-request message) names an accessory and `scope_redirect` otherwise; Python makes this choice, and words belonging to other intents in the same turn are not counted. Policy results validate known section references but do not prove factual grounding. Pydantic checks structure; it does not compute prices, authorize access, or establish policy eligibility. Catalog execution now populates `CatalogData.total_matches` with the pre-truncation match count and returns at most ten products in ascending ID order. This optional metadata preserves compatibility with existing internal result constructors; the search always supplies it. Multiple matches remain choices, never an implicit selection. See README for price and filter semantics.

## Trust boundary

The LLM proposes intents and extracts explicitly supplied information. The controller resolves records, validates business conditions, determines session access, and executes allowed functions. Pydantic validates structure and types; it does not establish authorization or business correctness.

Each turn produces an object with a nonempty `intents` list. Use a discriminated union on `type` and reject extra fields. Implemented bound: at most five intents per turn; ask the customer to narrow a larger request rather than silently dropping work. Permit one schema-repair attempt without executing invalid proposals, then return a standard error. These limits are configuration, not model decisions.

```json
{
  "intents": [{
    "type": "product_search",
    "query": "Yamaha C40",
    "category": null,
    "max_price_brl": null,
    "available_only": true,
    "quantity": 1,
    "payment_method": "pix",
    "installments": null
  }]
}
```

Unknown facts are null or absent, never guessed. Amounts are decimal strings, dates are ISO dates after unambiguous resolution, and quantities are positive integers. Validate dates against their meaning: an asserted past receipt cannot be in the future. Resolve relative dates using an injected clock and explicit store timezone; ask when ambiguous. Do not confuse local developer timezone with store timezone.

Defaults such as quantity one for a unit-price inquiry are controller-owned and must be visible in the resulting quote. Missing quantity for a basket assessment must not silently become one. Model-supplied customer IDs, prices, discounts, access claims, or executable statements are forbidden.

## Intent variants

| Type | Allowed extracted fields | Execution boundary |
| --- | --- | --- |
| `product_search` | query, category, max_price_brl, available_only, quantity, payment_method, installments | Resolve category/name; query, compute conditions, then filter by the requested payment price. |
| `order_status` | order_id | Query only within the authorized session; ask if order selection is missing. |
| `payment_options` | product_reference, quantity, payment_method, installments | Resolve product and calculate supported conditions. |
| `shipping_quote` | product_reference, quantity, destination, payment_method, installments | Calculate only supported cases; require confirmation or report unavailable otherwise. |
| `return_assessment` | order_id, reason, purchase_channel, received_at, condition | Evaluate supported rules with explicit provenance for declared facts. |
| `policy_question` | topic, question | Explain general policy; no individual approval or computed quote. |
| `complaint` | description | Acknowledge and explain the available next step; no false registration/transfer claim. |
| `out_of_scope` | topic | Politely redirect to store scope. |
| `small_talk` | kind | Template greeting, thanks, or goodbye. |

Implemented enums: payment method `pix`, `debit`, `credit`, `boleto`, `combined`; return reason `withdrawal`, `defect`, `preference`; purchase channel `online`, `in_store`; small-talk kind `greeting`, `thanks`, `goodbye`. Unknown or unsupported enum values are rejected structurally, never coerced into the nearest supported value. The extraction boundary permits one repair, then reports a stable error; customer-facing clarification belongs to the future controller. Combined payment is recognized as requiring confirmation until explicitly supported.

`product_reference` is a discriminated object: `{"kind":"query","query":"..."}`, `{"kind":"selected"}`, or `{"kind":"ordinal","ordinal":2}` (one-based displayed position). The controller assigns product IDs after lookup. Destination contains nullable customer-declared city, two-letter uppercase state, and postal code (eight digits, with an optional hyphen); neither alone proves metropolitan eligibility. Condition contains nullable booleans for original packaging, signs of use, complete accessories/manuals, and reported customization/final-sale notice. Preserve uncertainty rather than defaulting missing booleans to false.

For `shipping_quote`, preserve explicitly supplied payment conditions because the freight threshold uses the subtotal after applicable discounts. Python may reuse a validated quote only when product, quantity, and payment conditions match the current request; otherwise it recalculates or asks for missing conditions. Shipping clarification updates may supply `payment_method` and `installments`, as well as product reference, quantity, and destination, only when requested by the pending operation. Changes invalidate the dependent subtotal and freight calculation. Implemented (P10): `shipping_quote` reuses the payment quote, then requires a declared `destination.city`; it is supported only for Campo Grande with state MS or none (labeled assumption), with free freight above BRL 500, BRL 35 below, `requires_confirmation` (`FREE_FREIGHT_BOUNDARY`) at exactly BRL 500, `requires_confirmation` (`DELIVERY_REGION_UNCONFIRMED`) for other destinations, and `unavailable` (`PRODUCT_NOT_SHIPPABLE`) when the product is not available for the quantity. A failed or unavailable quote is reported before any destination is requested, and availability is checked before the region. Campo Grande without a state but with a postal code outside the 79xxx range requires region confirmation. A new payment or shipping quote for the selected product reuses quantity and payment facts from a pending quote of either type or, when none is pending, from the last successful quote of that same product (for example, “E o frete dele?” after a completed PIX quote, or a quantity correction keeping the payment method); a destination moves only between shipping quotes, and nothing moves to a different product. Reused facts from a completed quote are announced in the response. Only a successful quote of an available product is remembered; any other quote outcome, a new product search, or `/cancelar` forgets it. An ordinal or name reference does not reuse facts, even for the same product (limitation). `ShippingData` carries the product quote. Credit quotes carry `installment_amount_brl`, an optional `first_installment_brl` with the cent remainder, and `max_installments` when no count was declared; a count below the §3.1 minimum is cleared and noted in assumptions.

The controller determines required fields per case, not all possible fields for every intent. For example, a general return-policy question does not require an order ID. A case-specific return assessment cannot become a general answer merely to bypass missing facts.

Implemented return requirements (P11): without a reason, only `reason` is requested. Withdrawal (§4.1) requires `purchase_channel`, `received_at`, and `condition`; an in-store purchase is immediately `conditions_not_met`. Defect (§4.2) requires `order_id`, because its 30-day window starts at the recorded `order_date`; order access follows the order-lookup rules (no identity is `unauthorized`, foreign and nonexistent orders are the same `not_found`). Preference (§4.3) requires `condition` and always reports its seven-day window as `requires_review`. An order is optional for withdrawal and preference; when supplied and accessible, a non-delivered status or a receipt before the order date requires review. A declared defect always requires store inspection. Exclusions (§4.4) count against exchanges when declared true and are `unknown` when absent; for withdrawal, declared exclusions require review because §4.4 does not state its effect on §4.1. Any unsatisfied condition yields `conditions_not_met`; otherwise any unknown or review item yields `requires_review`. Windows use the store-date difference from the injected clock, with day zero on the starting date and the last day included. Receipt dates accept `today`, `yesterday`, `day_before_yesterday`, ISO `YYYY-MM-DD`, and Brazilian `DD/MM/YYYY` (added after the live model copied that format literally); dates without a year are rejected. An order number supplied by the model is discarded unless typed in the current message outside money amounts and date expressions (`dia 5`, `05/11`, ISO dates, `5 de novembro`); a receipt date is discarded unless its day number is typed in the current message or `hoje`/`ontem`/`anteontem` is used. When the declared receipt precedes the recorded order date, the withdrawal window requires review. A clarification that answers extra return facts is merged as a new turn with the pending declarations while other pending operations are kept, and a new return turn reuses facts declared for a pending return only for the same or no reason and the same or no order. Known limitation: product-condition booleans and the purchase channel are customer declarations interpreted by the model and are not checked against the message text; a model error can attribute an undeclared condition to the customer. Model-interpretation evaluations, not deterministic tests, must cover this.

## Clarification and session state

Maintain only session-lifetime state: simulated/authorized customer identity, bounded conversation history, last displayed products, selected product/order, and pending operations with collected facts. Provenance distinguishes system records from customer declarations.

For "this one", use a unique selected product; multiple possible products require clarification. An ordinal selection must refer to the actual list displayed before the current turn. Search results and successful product quotes share a global numbering sequence in first-display order, at most 50 distinct records per turn (five intents of up to ten results); one search returns at most ten. A `selected` reference can depend on a unique successful lookup earlier in the same turn, but an ordinal cannot predict unseen search results. A correction replaces the corresponding declared fact and invalidates dependent calculations.

During a pending operation, accept a narrowly scoped structured update to its allowed missing fields, identified by a controller-issued pending ID. This is an alternative clarification payload, not permission to mutate session identity or arbitrary state. Specify its Pydantic schema alongside the intent schemas. The controller cancels all pending operations on `/cancelar`; a new complete turn replaces prior pending work. Exception: a new `payment_options` intent whose reference is `selected` or absent, while a pending quote exists for the currently selected resolved product, reuses that quote's declared quantity and payment method when the new intent leaves them null. The check uses the selection current at that point of the turn, so a search earlier in the same turn prevents inheritance; a payment method is not inherited when the new intent supplies installments. Small models often answer a clarification this way instead of with an update; a quote for a different product inherits nothing. Clarification updates preserve other pending operations and re-evaluate only the target. A resolved product ID remains pinned when collecting other fields; unresolved references require an explicit reference update, not an unrelated later selection. Completed-request corrections use a new turn. These are initial controller behavior choices; automatic resumption of other pending operations is not implemented.

Execute independent intents in source order. Resolve dependent values from actual results, never from a model-predicted result. If one operation needs clarification, suspend its dependents but allow independent operations to complete. No concurrency or general-purpose dependency graph is required.

## Operation results

Use a typed result envelope and operation-specific data. Result IDs, provenance, and internal reason codes are assigned by Python.

```json
{
  "operation": "return_assessment",
  "status": "needs_information",
  "data": null,
  "missing_fields": ["purchase_channel", "received_at"],
  "reason_code": "RETURN_FACTS_MISSING",
  "policy_references": ["4.1"]
}
```

| Status | Meaning |
| --- | --- |
| `success` | Query or supported assessment completed. |
| `not_found` | No matching accessible record/result. |
| `needs_information` | Customer-supplied facts or a selection are missing. |
| `requires_confirmation` | Ambiguous policy or human decision blocks a commitment. |
| `unauthorized` | Session cannot access the operation/data. |
| `unavailable` | Required capability is not implemented or supported. |
| `error` | Technical execution failure. |

An out-of-stock lookup is `success` with an availability value in `data`. A negative assessment is also a business outcome, not a technical error. External order messages must not reveal whether another customer's order exists; render inaccessible and nonexistent references consistently where needed.

Product/quote data includes resolved product ID/name, requested quantity, availability, list price, applied promotion, effective payment condition, final amount, and assumptions. Order data includes only necessary status, recorded total, available tracking code and explicitly labeled delivery estimate. Return data states which conditions are satisfied, unknown, or require review; it must not claim a refund was authorized or performed.

No blanket exception swallowing: retain sanitized internal diagnostics while giving the user a stable error message. Do not invent an alternate price or policy when a function fails.

## General policy explanation

A controller-selected policy request may invoke the LLM with the reviewed manual and return:

```json
{
  "answer": "General explanation grounded in the supplied manual.",
  "policy_references": ["4.1"]
}
```

Validate structure and known section references. This does not prove semantic correctness: evaluate grounding separately. No individual approval, calculated price/date, contact conflict resolution, or claim of executed action is permitted through this route. Use deterministic blocks for especially sensitive conditions and known ambiguities. If the model fails, show a standard limitation rather than unsupported prose.

## Response composition

Render completed results first, then limitations, then one focused clarification (which may group closely related missing fields). When several operations are pending, the question names the first operation and states how many others are waiting. All operational numbers, stock, order facts, errors, and clarification questions are rendered in Python with Brazilian currency/date formatting. General policy prose is a separate block and cannot rewrite operational blocks. Do not display internal IDs/reason codes unnecessarily.

Acceptance examples: available Yamaha lookup plus PIX quote; discontinued product with stock; two-product ambiguity; seven-day return boundary with fixed receipt date; missing receipt date; exactly BRL 500 freight; forbidden discount stacking; foreign order access; model output containing unauthorized extra fields; one failed intent alongside an independent successful lookup.

Implementation references: [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/) and [discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/).
