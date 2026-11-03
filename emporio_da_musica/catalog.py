"""Deterministic snapshot catalog queries and nonstacking prices (§§3, 6)."""

import unicodedata
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contracts.intents import ProductSearch
from .contracts.results import CatalogData, ProductQuote, ProductSearchResult
from .data.records import Snapshot

MAX_CATALOG_RESULTS = 10
PIX_DISCOUNT_PERCENT = Decimal("5")  # Supplied manual §3.
CENT = Decimal("0.01")
# Supplied manual §3.1: (first count, last count, minimum installment). The 2–3
# band's minimum wording is ambiguous and requires confirmation instead.
INSTALLMENT_BANDS = ((4, 6, Decimal("80")), (7, 12, Decimal("100")))
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
        if 2 <= intent.installments <= 3:
            return ProductSearchResult(
                status="requires_confirmation",
                reason_code="AMBIGUOUS_INSTALLMENT_BAND",
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
