# Agent–Controller Contract

Status: proposed version 1, planning only. This refines the conversation into implementable boundaries; defaults introduced here must be reviewed with their implementation. No schemas or operations exist in code yet.

## Trust boundary

The LLM proposes intents and extracts explicitly supplied information. The controller resolves records, validates business conditions, determines session access, and executes allowed functions. Pydantic validates structure and types; it does not establish authorization or business correctness.

Each turn produces an object with a nonempty `intents` list. Use a discriminated union on `type` and reject extra fields. Proposed bound: at most five intents per turn; ask the customer to narrow a larger request rather than silently dropping work. Permit one schema-repair attempt without executing invalid proposals, then return a standard error. These limits are configuration, not model decisions.

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

Suggested enums: payment method `pix`, `debit`, `credit`, `boleto`; return reason `withdrawal`, `defect`, `preference`; purchase channel `online`, `in_store`; small-talk kind `greeting`, `thanks`, `goodbye`. Unknown or unsupported values trigger clarification, not coercion into the nearest supported value. Combined payment is recognized as requiring confirmation until explicitly supported.

`product_reference` is either a textual query or a reference to the session's selected product. The controller assigns product IDs after lookup. Destination contains customer-declared city and optional postal code; neither alone proves metropolitan eligibility. Condition contains nullable booleans for original packaging, signs of use, complete accessories/manuals, and reported customization/final-sale notice. Preserve uncertainty rather than defaulting missing booleans to false.

For `shipping_quote`, preserve explicitly supplied payment conditions because the freight threshold uses the subtotal after applicable discounts. Python may reuse a validated quote only when product, quantity, and payment conditions match the current request; otherwise it recalculates or asks for missing conditions. Shipping clarification updates may supply `payment_method` and `installments`, as well as product reference, quantity, and destination, only when requested by the pending operation. Changes invalidate the dependent subtotal and freight calculation.

The controller determines required fields per case, not all possible fields for every intent. For example, a general return-policy question does not require an order ID. A case-specific return assessment cannot become a general answer merely to bypass missing facts.

## Clarification and session state

Maintain only session-lifetime state: simulated/authorized customer identity, bounded conversation history, last displayed products, selected product/order, and pending operations with collected facts. Provenance distinguishes system records from customer declarations.

For "this one", use a unique selected product; multiple possible products require clarification. An ordinal selection must refer to the actual displayed list. A correction replaces the corresponding declared fact and invalidates dependent calculations.

During a pending operation, accept a narrowly scoped structured update to its allowed missing fields, identified by a controller-issued pending ID. This is an alternative clarification payload, not permission to mutate session identity or arbitrary state. Specify its Pydantic schema alongside the intent schemas. The controller can cancel or replace a pending operation when the customer changes direction.

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

Render completed results first, then limitations, then one focused clarification (which may group closely related missing fields). All operational numbers, stock, order facts, errors, and clarification questions are rendered in Python with Brazilian currency/date formatting. General policy prose is a separate block and cannot rewrite operational blocks. Do not display internal IDs/reason codes unnecessarily.

Acceptance examples: available Yamaha lookup plus PIX quote; discontinued product with stock; two-product ambiguity; seven-day return boundary with fixed receipt date; missing receipt date; exactly BRL 500 freight; forbidden discount stacking; foreign order access; model output containing unauthorized extra fields; one failed intent alongside an independent successful lookup.
