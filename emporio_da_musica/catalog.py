"""Deterministic snapshot catalog queries and nonstacking prices (§§3, 6)."""

import unicodedata
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contracts.intents import ProductSearch
from .contracts.results import CatalogData, ProductQuote, ProductSearchResult
from .data.records import Snapshot

MAX_CATALOG_RESULTS = 10
PIX_DISCOUNT_PERCENT = Decimal("5")  # Supplied manual §3.
CENT = Decimal("0.01")


def normalize(text: str) -> str:
    """Ignore case, accents, and repeated whitespace; retain punctuation."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return " ".join(
        "".join(c for c in decomposed if not unicodedata.combining(c)).split()
    )


def search_catalog(snapshot: Snapshot, intent: ProductSearch) -> ProductSearchResult:
    """Return ordered choices, never implicitly select an ambiguous product.

    Missing quantity means an explicitly labeled unit-price catalog inquiry only.
    A budget limits the requested quantity's total, after rounding each unit.
    """
    return _search(snapshot, intent)


def quote_product(
    snapshot: Snapshot, product_id: int, intent: ProductSearch
) -> ProductSearchResult:
    """Quote an exact Python-resolved ID, never a model-provided identifier."""
    return _search(snapshot, intent, product_id=product_id)


def _search(snapshot, intent, *, product_id=None):
    if intent.payment_method == "combined":
        return ProductSearchResult(
            status="requires_confirmation",
            reason_code="COMBINED_PAYMENT_REQUIRES_CONFIRMATION",
            policy_references=("3",),
        )
    if intent.installments is not None:
        if intent.payment_method is None:
            return ProductSearchResult(
                status="needs_information",
                missing_fields=("payment_method",),
                reason_code="PAYMENT_METHOD_MISSING",
            )
        if intent.payment_method != "credit":
            return ProductSearchResult(
                status="needs_information",
                missing_fields=("payment_method", "installments"),
                reason_code="INCOMPATIBLE_PAYMENT_CONDITIONS",
            )
        if intent.installments > 1:
            return ProductSearchResult(
                status=(
                    "requires_confirmation"
                    if intent.installments <= 3
                    else "unavailable"
                ),
                reason_code=(
                    "AMBIGUOUS_INSTALLMENT_BAND"
                    if intent.installments <= 3
                    else "INSTALLMENT_QUOTE_NOT_SUPPORTED"
                ),
                policy_references=("3.1",),
            )

    quantity = intent.quantity if intent.quantity is not None else 1
    assumptions = (
        () if intent.quantity is not None else ("Unit-price inquiry: quantity 1.",)
    )
    if intent.payment_method is None:
        assumptions += (
            "Payment unspecified: list or active promotional price; no PIX discount.",
        )
    query = normalize(intent.query or "")
    category = normalize(intent.category or "")
    quotes = []
    for product in sorted(snapshot.products.values(), key=lambda p: p.product_id):
        if product_id is not None and product.product_id != product_id:
            continue
        if query not in normalize(product.name):
            continue
        if category not in normalize(snapshot.categories[product.category_id].name):
            continue
        availability = (
            product.status
            if product.status != "active"
            else "available"
            if product.stock_quantity >= quantity
            else "insufficient_stock"
        )
        if intent.available_only is True and availability != "available":
            continue
        promotions = [
            p for p in snapshot.promotions_by_product[product.product_id] if p.is_active
        ]
        if len(promotions) > 1:
            return ProductSearchResult(
                status="requires_confirmation",
                reason_code="MULTIPLE_ACTIVE_PROMOTIONS",
                policy_references=("6",),
            )
        promotion = promotions[0].discount_percent if promotions else None
        discount = (
            promotion
            if promotion is not None
            else PIX_DISCOUNT_PERCENT
            if intent.payment_method == "pix"
            else Decimal(0)
        )
        # Source numeric fields have no digit limit. Avoid ambient Decimal precision
        # changing a quote or making large valid records fail during quantization.
        with localcontext() as context:
            context.prec = max(
                28,
                len(product.price_brl.as_tuple().digits)
                + len(discount.as_tuple().digits)
                + abs(discount.as_tuple().exponent)
                + len(str(quantity))
                + 10,
            )
            unit = (product.price_brl * (1 - discount / 100)).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            total = unit * quantity
        if intent.max_price_brl is not None and total > intent.max_price_brl:
            continue
        quotes.append(
            ProductQuote(
                product_id=product.product_id,
                name=product.name,
                quantity=quantity,
                availability=availability,
                list_unit_price_brl=product.price_brl,
                promotion_percent=promotion,
                payment_method=intent.payment_method,
                installments=intent.installments,
                final_total_brl=total,
                assumptions=assumptions,
            )
        )
    if not quotes:
        return ProductSearchResult(status="not_found", reason_code="NO_CATALOG_MATCH")
    return ProductSearchResult(
        status="success",
        data=CatalogData(
            products=tuple(quotes[:MAX_CATALOG_RESULTS]),
            total_matches=len(quotes),
        ),
        policy_references=("3", "6"),
    )
