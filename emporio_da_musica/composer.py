"""Portuguese operational responses, composed exclusively from Python results."""

from decimal import Decimal

from .contracts.results import CatalogData, OrderData, ProductQuote

AVAILABILITY = {
    "available": "disponível para a quantidade solicitada",
    "insufficient_stock": "estoque insuficiente",
    "discontinued": "descontinuado; indisponível para venda",
    "coming_soon": "lançamento futuro; indisponível para venda",
}
PAYMENTS = {
    None: "pagamento não informado",
    "pix": "PIX",
    "debit": "débito",
    "credit": "crédito",
    "boleto": "boleto",
}
FIELDS = {
    "product_reference": "o produto (nome ou número da lista)",
    "quantity": "a quantidade",
    "payment_method": "a forma de pagamento",
    "installments": "o número de parcelas",
    "order_id": "o número do pedido",
}
OPERATIONS = {
    "order_status": "a consulta do pedido",
    "payment_options": "a cotação",
}
ORDER_STATUS = {
    "pending": "aguardando confirmação",
    "confirmed": "confirmado, aguardando envio",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
REASONS = {
    "NO_CATALOG_MATCH": "Não encontrei produtos com esses critérios.",
    "COMBINED_PAYMENT_REQUIRES_CONFIRMATION": "Pagamento combinado precisa de confirmação da loja. Não solicitei essa confirmação.",
    "AMBIGUOUS_INSTALLMENT_BAND": "A regra para 2–3 parcelas precisa de confirmação da loja. Não solicitei essa confirmação.",
    "INSTALLMENT_QUOTE_NOT_SUPPORTED": "O cálculo desse parcelamento ainda não está disponível.",
    "MULTIPLE_ACTIVE_PROMOTIONS": "Há promoções ativas conflitantes; o preço precisa de confirmação da loja.",
    "OPERATION_NOT_SUPPORTED": "Essa operação ainda não está disponível nesta demonstração.",
    "OPERATION_FAILED": "Não consegui concluir essa consulta. Tente novamente.",
    "ORDER_ACCESS_DENIED": "Para consultar pedidos, é preciso iniciar a sessão de demonstração com um cliente simulado; nenhum pedido foi consultado.",
    "ORDER_NOT_ACCESSIBLE": "Não encontrei esse pedido entre os pedidos do cliente desta sessão. Confira o número informado.",
}


CATALOG_FOOTER = "Valores e disponibilidade do arquivo de dados; nenhuma compra ou reserva foi realizada."
ORDER_FOOTER = "Dados do registro histórico do pedido, sem consulta em tempo real à transportadora; nenhuma alteração foi feita."


def money(amount: Decimal) -> str:
    return "R$ " + format(amount, ",.2f").translate(str.maketrans(",.", ".,"))


def safe_text(value: str) -> str:
    """Prevent source text from emitting terminal control sequences or fake lines."""
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def render_quote(quote: ProductQuote) -> str:
    parts = [
        f"{safe_text(quote.name)} — {AVAILABILITY[quote.availability]}.",
        f"Preço de tabela por unidade: {money(quote.list_unit_price_brl)}.",
    ]
    if quote.promotion_percent is not None:
        percent = format(quote.promotion_percent, "f").replace(".", ",")
        parts.append(f"Promoção ativa: {percent}% (sem desconto PIX adicional).")
    elif quote.payment_method == "pix":
        parts.append("Desconto PIX: 5%.")
    parts.append(
        f"Total para {quote.quantity} unidade(s): {money(quote.final_total_brl)} ({PAYMENTS[quote.payment_method]})."
    )
    if "Unit-price inquiry: quantity 1." in quote.assumptions:
        parts.append("Consulta de preço unitário: quantidade considerada igual a 1.")
    if quote.payment_method is None:
        parts.append("Sem desconto PIX enquanto o pagamento não for informado.")
    return " ".join(parts)


def render_order(order: OrderData) -> str:
    lines = [
        f"Pedido {order.order_id}: {ORDER_STATUS[order.status]}.",
        f"Total registrado no pedido: {money(order.recorded_total_brl)}.",
    ]
    if order.tracking_code:
        lines.append(f"Código de rastreio: {safe_text(order.tracking_code)}.")
    else:
        lines.append("Código de rastreio: ainda não registrado.")
    if order.estimated_delivery:
        lines.append(
            "Previsão de entrega (estimativa, não confirma o recebimento): "
            + order.estimated_delivery.strftime("%d/%m/%Y")
            + "."
        )
    else:
        lines.append("Previsão de entrega: ainda não registrada.")
    return " ".join(lines)


def compose(results, displayed_ids: tuple[int, ...], pending) -> str:
    completed, limitations, footers = [], [], []
    for result in results:
        if result.status == "success":
            if isinstance(result.data, CatalogData):
                lines = [
                    f"{displayed_ids.index(q.product_id) + 1}. {render_quote(q)}"
                    for q in result.data.products
                ]
                if result.data.total_matches > len(result.data.products):
                    lines.append(
                        f"Mostrando {len(result.data.products)} de {result.data.total_matches} resultados; refine a busca para ver outros."
                    )
                completed.append("\n".join(lines))
                footers.append(CATALOG_FOOTER)
            elif isinstance(result.data, ProductQuote):
                position = displayed_ids.index(result.data.product_id) + 1
                completed.append(f"{position}. {render_quote(result.data)}")
                footers.append(CATALOG_FOOTER)
            elif isinstance(result.data, OrderData):
                completed.append(render_order(result.data))
                footers.append(ORDER_FOOTER)
        elif result.status != "needs_information":
            limitations.append(
                REASONS.get(
                    result.reason_code, "Não foi possível concluir essa operação."
                )
            )
    blocks = completed + limitations
    blocks.extend(dict.fromkeys(footers))
    if pending:
        # One focused question at a time; other waiting operations are announced.
        first = pending[0]
        labels = [FIELDS.get(f, "os dados solicitados") for f in first.requested_fields]
        subject = (
            f" {OPERATIONS.get(first.declarations.intent.type, 'a consulta')}"
            if len(pending) > 1
            else ""
        )
        blocks.append(f"Para continuar{subject}, informe " + ", ".join(labels) + ".")
        if len(pending) > 1:
            blocks.append(
                f"Depois disso, ainda há {len(pending) - 1} consulta(s) aguardando dados."
            )
    return "\n\n".join(blocks)
