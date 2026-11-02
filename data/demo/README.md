# Demonstration snapshot

This dataset is derived from the fictional Empório da Música technical challenge supplied for this project. It is bundled so evaluators can run the data-validation command immediately after cloning, without obtaining the original download. It is a static demonstration, not live operational data.

## Preparation and provenance

The original CSVs were validated before preparation. Categories, products, promotions, and order items were copied unchanged. For customers, all names, phone numbers, emails, and cities were replaced with deterministic synthetic values:

- Name: `Demo Customer <customer_id>`.
- Phone: `00000000000`, a non-contactable placeholder.
- Email: `customer-<customer_id>@example.invalid`.
- City: `Campo Grande` for every demo customer, independent of the source city.

For orders, nonempty tracking codes were replaced with `DEMO-ORDER-<order_id>` and nonempty notes with `Synthetic demonstration note.` Empty values remain empty. Demo tracking codes cannot be used with carriers. Original customer identifiers and order relationships are preserved solely to retain the challenge scenarios; no customer identity mapping is published.

Order dates, statuses, payment methods, recorded totals, delivery estimates, item quantities, and all catalog/promotion facts remain as supplied. Historical totals are deliberately not reconciled with current prices. These records do not establish actual receipt, purchase channel, or production authentication. Customer city is not a delivery address or proof of eligibility.

The snapshot contains 9 categories, 65 products, 50 synthetic customers, 20 orders, 22 order items, and 25 promotions. It preserves inactive promotions, missing order fields, empty categories, unavailable product statuses, and recorded totals that differ from current catalog totals. Loader tests use separate small synthetic fixtures; a dedicated demo check verifies this bundled dataset and its synthetic field conventions.

## Usage

From the repository root, after installing the documented environment:

```sh
.venv/bin/python -m emporio_da_musica
```

This currently validates the data and prints counts; the conversational assistant is a later milestone. To use the original files, pass their directory explicitly. Keep originals outside this tracked demo folder, for example in the ignored `data/source/` directory. The original policy PDF is not included or required for this command.
