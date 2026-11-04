"""Deterministic snapshot catalog queries and nonstacking prices (§§3, 6)."""

import unicodedata
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contracts.intents import ProductSearch
from .contracts.results import CatalogData, ProductQuote, ProductSearchResult
from .data.records import Snapshot

MAX_CATALOG_RESULTS = 10
PIX_DISCOUNT_PERCENT = Decimal("5")  # Supplied manual §3.
CENT = Decimal("0.01")
# Supplied manual §3.1: (first count, last count, minimum installment).
INSTALLMENT_BANDS = ((4, 6, Decimal("80")), (7, 12, Decimal("100")))
# The 2–3 band's wording is ambiguous (no minimum, "except below BRL 50") and the §3
# table says BRL 100. An installment of at least BRL 100 satisfies every reading.
SMALL_BAND_SAFE_MINIMUM = Decimal("100")
COMBINED_PAYMENT_MINIMUM = Decimal("2000")  # Supplied manual §3.1.
INSTALLMENT_MINIMUM_NOT_MET = "Requested installments do not meet the minimum."


def installment_minimum(count: int) -> Decimal | None:
    for first, last, minimum in INSTALLMENT_BANDS:
        if first <= count <= last:
            return minimum
    return None


def split_installments(total: Decimal, count: int) -> tuple[Decimal, Decimal]:
    """Equal installments in whole cents; the first carries the remainder."""
    cents = int((total / CENT).to_integral_value())
    base, remainder = divmod(cents, count)
    return Decimal(base) * CENT, Decimal(base + remainder) * CENT


def max_installments(total: Decimal) -> int | None:
    """Largest count in the unambiguous bands whose installments meet the minimum."""
    for count in range(12, 3, -1):
        if split_installments(total, count)[0] >= installment_minimum(count):
            return count
    return None


def max_small_installments(total: Decimal) -> int | None:
    """Largest of 3 and 2 installments that every reading of §3.1 allows."""
    for count in (3, 2):
        if split_installments(total, count)[0] >= SMALL_BAND_SAFE_MINIMUM:
            return count
    return None


def normalize(text: str) -> str:
    """Ignore case, accents, and repeated whitespace; retain punctuation."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return " ".join(
        "".join(c for c in decomposed if not unicodedata.combining(c)).split()
    )


CATEGORY_IGNORED = "Requested name and category had no joint match; one was ignored."


def search_catalog(snapshot: Snapshot, intent: ProductSearch) -> ProductSearchResult:
    """Return ordered choices, never implicitly select an ambiguous product.

    Missing quantity means an explicitly labeled unit-price catalog inquiry only.
    A budget limits the requested quantity's total, after rounding each unit.
    A named product with a model-guessed category that matches nothing is searched
    again by name only, and every resulting quote states that assumption.
    """
    result = _search(snapshot, intent)
    if result.status != "not_found" or not intent.query or not intent.category:
        return result
    retry = _search(snapshot, intent.model_copy(update={"category": None}))
    if retry.status != "success":
        return result
    products = tuple(
        q.model_copy(update={"assumptions": (*q.assumptions, CATEGORY_IGNORED)})
        for q in retry.data.products
    )
    return retry.model_copy(
        update={"data": retry.data.model_copy(update={"products": products})}
    )


def quote_product(
    snapshot: Snapshot, product_id: int, intent: ProductSearch
) -> ProductSearchResult:
    """Quote an exact Python-resolved ID, never a model-provided identifier."""
    return _search(snapshot, intent, product_id=product_id)


def _combined_payment(snapshot, intent, product_id):
    """State the §3.1 threshold; a split and its discounts stay for the store."""
    reason = "COMBINED_PAYMENT_REQUIRES_CONFIRMATION"
    priced = _search(
        snapshot,
        intent.model_copy(update={"payment_method": None, "installments": None}),
        product_id=product_id,
    )
    if priced.status == "not_found":
        return priced
    single = (
        priced.data.products[0]
        if priced.status == "success" and len(priced.data.products) == 1
        else None
    )
    if single and single.availability != "available":
        return priced  # Stock and status come before any payment condition.
    # A refusal needs the real quantity; "above" excludes exactly the threshold.
    if (
        single
        and intent.quantity is not None
        and single.final_total_brl <= COMBINED_PAYMENT_MINIMUM
    ):
        reason = "COMBINED_PAYMENT_BELOW_MINIMUM"
    return ProductSearchResult(
        status="requires_confirmation",
        reason_code=reason,
        policy_references=("3.1",),
    )


def _search(snapshot, intent, *, product_id=None):
    if intent.payment_method == "combined":
        return _combined_payment(snapshot, intent, product_id)
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
    # Without the exact phrase, "GD20 Natural" still finds "GD20 Dreadnought Natural".
    exact_phrase = any(query in normalize(p.name) for p in snapshot.products.values())
    quotes = []
    for product in sorted(snapshot.products.values(), key=lambda p: p.product_id):
        if product_id is not None and product.product_id != product_id:
            continue
        name = normalize(product.name)
        if exact_phrase:
            if query not in name:
                continue
        elif not all(
            word in name.split() if word.isdigit() else word in name
            for word in query.split()
        ):
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
        installments = intent.installments
        credit = {}
        if intent.payment_method is None:
            credit["stock_quantity"] = product.stock_quantity
            credit["max_installments"] = max_installments(total)
            credit["pix_total_brl"] = (
                total
                if promotion is not None
                else (product.price_brl * (1 - PIX_DISCOUNT_PERCENT / 100)).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                * quantity
            )
        product_assumptions = assumptions
        if intent.payment_method == "credit":
            if installments is None:
                credit["max_installments"] = max_installments(total)
            elif 2 <= installments <= 3:
                base, first = split_installments(total, installments)
                if base < SMALL_BAND_SAFE_MINIMUM:
                    return ProductSearchResult(
                        status="requires_confirmation",
                        reason_code="AMBIGUOUS_INSTALLMENT_BAND",
                        policy_references=("3.1",),
                    )
                credit["installment_amount_brl"] = base
                if first != base:
                    credit["first_installment_brl"] = first
            elif installments >= 4:
                base, first = split_installments(total, installments)
                if base >= installment_minimum(installments):
                    credit["installment_amount_brl"] = base
                    if first != base:
                        credit["first_installment_brl"] = first
                else:
                    # Shown as a note; the requested count is not offered.
                    installments = None
                    credit["max_installments"] = max_installments(total)
                    product_assumptions += (INSTALLMENT_MINIMUM_NOT_MET,)
        quotes.append(
            ProductQuote(
                product_id=product.product_id,
                name=product.name,
                quantity=quantity,
                availability=availability,
                list_unit_price_brl=product.price_brl,
                promotion_percent=promotion,
                payment_method=intent.payment_method,
                installments=installments,
                final_total_brl=total,
                assumptions=product_assumptions,
                **credit,
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
        policy_references=("3", "3.1", "6")
        if intent.payment_method == "credit"
        else ("3", "6"),
    )
