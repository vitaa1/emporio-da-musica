"""Portuguese operational responses, composed exclusively from Python results."""

from decimal import Decimal

from .catalog import CATEGORY_IGNORED
from .contracts.results import (
    CatalogData,
    ComplaintData,
    OrderData,
    OutOfScopeData,
    PolicyData,
    ProductQuote,
    ReturnData,
    SmallTalkData,
)

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
    "reason": "o motivo: arrependimento de compra online, defeito de fabricação ou troca por preferência (cor, modelo, tamanho)",
    "purchase_channel": "se a compra foi feita online ou na loja física",
    "received_at": "a data em que você recebeu o produto (por exemplo, 01/11/2026, hoje ou ontem)",
    "condition": "o estado do produto (se está na embalagem original, se tem sinais de uso, se tem todos os acessórios e manuais, se tem personalização ou ajuste sob encomenda e se foi comprado com aviso de venda final)",
}
OPERATIONS = {
    "order_status": "a consulta do pedido",
    "payment_options": "a cotação",
    "return_assessment": "a avaliação de troca ou devolução",
}
TEMPLATES = {
    "greeting": "Olá! Que bom ter você por aqui no Empório da Música. Posso ajudar com instrumentos, preços, pedidos e políticas da loja.",
    "thanks": "Imagina, foi um prazer ajudar! Se precisar de mais alguma coisa, é só chamar.",
    "goodbye": "Até mais! Boa música e conte com a gente quando precisar.",
    "scope_redirect": "Esse assunto foge do que eu consigo atender. O Empório da Música trabalha exclusivamente com instrumentos musicais — não vendemos acessórios como cordas, cabos, palhetas, pedais, amplificadores ou cases, e não indico outras lojas. Posso ajudar você a encontrar um instrumento?",
    "complaint_acknowledgment": "Sinto muito pela experiência, e obrigado por nos contar. Eu não consigo registrar reclamações nem encaminhar o atendimento por aqui, então nada foi registrado ainda. Para formalizar, procure a equipe da loja (Rua 14 de Maio, 3200 — Centro, Campo Grande/MS); pelo manual, o retorno da equipe é previsto em até 24 horas úteis após o registro.",
}
POLICY_FOOTER = "Explicação geral com base no manual da loja; casos específicos dependem dos dados do pedido e não foram aprovados aqui."
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
    "POLICY_MODEL_UNAVAILABLE": "Explicações sobre as políticas da loja exigem o modelo de linguagem e não estão disponíveis no modo de demonstração por comandos.",
    "POLICY_ANSWER_FAILED": "Não consegui responder sobre essa política agora. Tente reformular a pergunta; não vou arriscar uma informação incorreta.",
    "CONTACT_CONFLICT": "O manual da loja traz telefones e e-mails divergentes, então não posso indicar um contato oficial com segurança. O endereço da loja é Rua 14 de Maio, 3200 — Centro, Campo Grande/MS, CEP 79202-333 (manual, seção 1.2).",
    "ORDER_NOT_ACCESSIBLE": "Não encontrei esse pedido entre os pedidos do cliente desta sessão. Confira o número informado.",
}


RETURN_PROCESS = {
    "withdrawal": "devolução por arrependimento",
    "defect": "troca por defeito",
    "preference": "troca por preferência",
}
RETURN_ASSESSMENT = {
    "conditions_met": "Pelas informações disponíveis, as condições do manual para {process} estão atendidas.",
    "conditions_not_met": "Pelas informações disponíveis, as condições do manual para {process} não estão atendidas.",
    "requires_review": "Avaliação de {process}: alguns pontos ainda não estão confirmados.",
}
RETURN_CONDITIONS = {
    "online_purchase": "compra feita online (o direito de arrependimento vale para compras online)",
    "within_7_days_of_receipt": "até 7 dias corridos após o recebimento",
    "order_delivered": "pedido registrado como entregue",
    "receipt_after_order": "data de recebimento compatível com a data do pedido",
    "original_packaging": "embalagem original",
    "no_signs_of_use": "sem sinais de uso",
    "complete_accessories_manuals": "todos os acessórios e manuais",
    "not_customized": "sem personalização ou ajuste sob encomenda",
    "not_final_sale": "sem aviso de venda final",
    "within_30_days_of_purchase": "até 30 dias corridos após a compra",
    "manufacturing_defect": "defeito de fabricação, sem danos por mau uso, queda, umidade ou modificação",
    "preference_window": "prazo de 7 dias (o manual não define se conta da compra ou do recebimento)",
    "desired_product_available": "disponibilidade do produto desejado",
}
CONDITION_STATES = {
    "satisfied": "atendida",
    "not_satisfied": "não atendida",
    "unknown": "não informada",
    "requires_review": "precisa de avaliação da loja",
}
PROVENANCE = {
    "system_record": "registro do pedido",
    "customer_declaration": "informado por você",
    "policy": "manual da loja",
    "unknown": "sem informação",
}
RETURN_FOOTER = "Avaliação preliminar com base no manual e nas informações disponíveis; nenhuma devolução, troca ou reembolso foi solicitado, aprovado ou realizado. Para dar andamento, procure a equipe da loja."

BUDGET_IGNORED = "O limite de preço não foi reconhecido nesta mensagem e não foi aplicado; informe o valor em números (por exemplo, até R$ 1000)."
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


def render_return(data: ReturnData, references) -> str:
    process = RETURN_PROCESS[data.reason]
    lines = [RETURN_ASSESSMENT[data.assessment].format(process=process)]
    for condition in data.conditions:
        lines.append(
            f"- {RETURN_CONDITIONS[condition.name]}: "
            f"{CONDITION_STATES[condition.state]} ({PROVENANCE[condition.provenance]})."
        )
    names = {c.name: c.state for c in data.conditions}
    if names.get("online_purchase") == "not_satisfied":
        lines.append(
            "Compras na loja física podem ser avaliadas como troca por defeito ou por preferência."
        )
    if data.reason == "withdrawal" and data.assessment != "conditions_not_met":
        lines.append(
            "Pelo manual, o reembolso é feito na mesma forma de pagamento original em até 10 dias úteis, e o frete de devolução fica por conta da loja."
        )
    if names.get("within_30_days_of_purchase") == "not_satisfied":
        lines.append(
            "Depois de 30 dias, o defeito é tratado pela garantia do fabricante; a loja pode intermediar o processo mediante solicitação."
        )
    lines.append(f"(Manual da loja, seção {', '.join(references)}.)")
    return "\n".join(lines)


def compose(results, displayed_ids: tuple[int, ...], pending, notes=()) -> str:
    completed, limitations, footers = [], [], []
    for result in results:
        if result.status == "success":
            if isinstance(result.data, CatalogData):
                lines = [
                    f"{displayed_ids.index(q.product_id) + 1}. {render_quote(q)}"
                    for q in result.data.products
                ]
                if any(CATEGORY_IGNORED in q.assumptions for q in result.data.products):
                    lines.append(
                        "Busca ampliada: o nome e a categoria juntos não tinham resultado."
                    )
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
            elif isinstance(result.data, ReturnData):
                completed.append(render_return(result.data, result.policy_references))
                footers.append(RETURN_FOOTER)
            elif isinstance(result.data, PolicyData):
                sections = ", ".join(result.data.policy_references)
                completed.append(
                    f"{safe_text(result.data.answer)} (Manual da loja, seção {sections}.)"
                )
                footers.append(POLICY_FOOTER)
            elif isinstance(
                result.data, (SmallTalkData, OutOfScopeData, ComplaintData)
            ):
                completed.append(TEMPLATES[result.data.template])
        elif result.status != "needs_information":
            limitations.append(
                REASONS.get(
                    result.reason_code, "Não foi possível concluir essa operação."
                )
            )
    blocks = completed + limitations + list(notes)
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
