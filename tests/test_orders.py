"""Session-scoped order lookup: authorization, nondisclosure, and missing facts."""

import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

import pytest

from emporio_da_musica.cli import run_cli
from emporio_da_musica.controller import Controller
from emporio_da_musica.data.records import Customer, Order
from emporio_da_musica.providers.demo import DemoProvider

from .support import FakeProvider, search, turn, update


def order(order_id, customer_id, status, total, tracking=None, estimate=None):
    return Order(
        order_id,
        customer_id,
        date(2026, 2, 1),
        status,
        Decimal(total),
        "pix",
        tracking,
        estimate,
        None,
    )


@pytest.fixture
def snapshot(app):
    orders = {
        1: order(1, 1, "shipped", "349.90", "SYN-TRACK-1", date(2026, 2, 28)),
        2: order(2, 1, "confirmed", "1400"),
        3: order(3, 2, "delivered", "999", "SYN-TRACK-3", date(2026, 1, 10)),
    }
    return replace(
        app.snapshot,
        customers={
            1: Customer(1, "Synthetic One", "0", "one@example.test", "City"),
            2: Customer(2, "Synthetic Two", "0", "two@example.test", "City"),
        },
        orders=orders,
        orders_by_customer={1: (orders[1], orders[2]), 2: (orders[3],)},
    )


def controller(snapshot, customer_id=1):
    return Controller(
        snapshot,
        FakeProvider(),
        clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc),
        customer_id=customer_id,
    )


def lookup(order_id=None):
    return {"type": "order_status", "order_id": order_id}


def test_own_order_renders_status_tracking_and_labeled_estimate(snapshot):
    app = controller(snapshot)
    response = turn(app, lookup(1), message="pedido 1")
    data = response.results[0].data
    assert data.order_id == 1 and data.status == "shipped"
    assert "Pedido 1: enviado." in response.text
    assert "R$ 349,90" in response.text
    assert "SYN-TRACK-1" in response.text
    assert "estimativa, não confirma o recebimento): 28/02/2026" in response.text
    assert app.session.selected_order_id == 1


def test_recorded_total_is_preserved_and_missing_fields_not_fabricated(snapshot):
    app = controller(snapshot)
    response = turn(app, lookup(2), message="pedido 2")
    assert response.results[0].data.recorded_total_brl == Decimal("1400")
    assert response.results[0].data.tracking_code is None
    assert response.results[0].data.estimated_delivery is None
    assert "Código de rastreio: ainda não registrado." in response.text
    assert "Previsão de entrega: ainda não registrada." in response.text


def test_foreign_and_nonexistent_orders_are_indistinguishable(snapshot):
    app = controller(snapshot)
    foreign = turn(app, lookup(3), message="pedido 3")
    missing = turn(app, lookup(999), message="pedido 999")
    assert foreign.text == missing.text
    assert foreign.results[0].status == missing.results[0].status == "not_found"
    assert foreign.results[0].reason_code == missing.results[0].reason_code
    for text in (foreign.text, missing.text):
        assert "SYN-TRACK-3" not in text and "Synthetic" not in text
        assert "R$" not in text
    assert app.session.selected_order_id is None


def test_without_identity_no_order_is_consulted(snapshot):
    app = controller(snapshot, customer_id=None)
    response = turn(app, lookup(1), message="pedido 1")
    assert response.results[0].status == "unauthorized"
    assert "SYN-TRACK-1" not in response.text


def test_unknown_startup_identity_is_rejected(snapshot):
    with pytest.raises(ValueError):
        controller(snapshot, customer_id=99)


def test_missing_order_id_asks_then_accepts_pending_update(snapshot):
    app = controller(snapshot)
    response = turn(app, lookup())
    assert response.results[0].status == "needs_information"
    assert response.results[0].missing_fields == ("order_id",)
    assert "informe o número do pedido" in response.text
    response = update(app, "é o 2", order_id=2)
    assert response.results[0].status == "success"
    assert not app.session.pending


def test_follow_up_without_number_uses_order_in_focus(snapshot):
    app = controller(snapshot)
    turn(app, lookup(1), message="pedido 1")
    response = turn(app, lookup())
    assert response.results[0].data.order_id == 1
    turn(app, lookup(3), message="pedido 3")
    assert app.session.selected_order_id is None
    response = turn(app, lookup())
    assert response.results[0].status == "needs_information"


def test_order_and_catalog_in_one_turn_keep_separate_footers(snapshot):
    app = controller(snapshot)
    response = turn(app, search("Piano"), lookup(1), message="pedido 1")
    assert [r.status for r in response.results] == ["success", "success"]
    assert "Nada foi comprado ou reservado" in response.text
    assert "sem consulta em tempo real à transportadora" in response.text


def test_provider_request_never_carries_identity_or_order_records(snapshot):
    app = controller(snapshot)
    turn(app, lookup(1), message="pedido 1")
    request = app.provider.requests[0]
    assert not hasattr(request, "customer_id")
    assert "Synthetic" not in repr(request)


def test_demo_cli_order_command_with_simulated_identity(snapshot):
    app = controller(snapshot)
    app.provider = DemoProvider()
    output = StringIO()
    run_cli(app, StringIO("/pedido\n/pedido 1\n/pedido x\n/sair\n"), output)
    text = output.getvalue()
    assert "cliente simulado 1" in text and "não é autenticação" in text
    assert "informe o número do pedido" in text
    assert "Pedido 1: enviado." in text
    assert "Use /pedido NUMERO" in text


def test_cli_rejects_unknown_customer_id():
    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica.cli", "--demo", "--customer-id", "0"],
        input="/sair\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Unknown simulated customer" in result.stderr


def test_cli_bundled_demo_order_lookup():
    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica.cli", "--demo", "--customer-id", "1"],
        input="/pedido 4\n/pedido 1\n/sair\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Pedido 4: entregue." in result.stdout
    assert "R$ 799,90" in result.stdout
    assert "Não encontrei esse pedido" in result.stdout


def test_order_number_absent_from_current_message_is_ignored(snapshot):
    app = controller(snapshot)
    turn(app, lookup(3), message="pedido 3")
    # Synthetic message has no digits: a model-copied number must not be used.
    response = turn(app, lookup(3))
    assert response.results[0].status == "needs_information"
    app.provider.responses.append({"intents": [lookup(1)]})
    response = app.handle("e o pedido 1?")
    assert response.results[0].data.order_id == 1
    response = turn(app, lookup(2))
    assert response.results[0].data.order_id == 1


def test_other_typed_number_never_falls_back_to_focused_order(snapshot):
    app = controller(snapshot)
    turn(app, lookup(1), message="pedido 1")
    # The model copies the focused order although the customer typed another one.
    response = turn(app, lookup(1), message="e o pedido 7?")
    assert response.results[0].status == "needs_information"
    assert "Pedido 1" not in response.text
    response = turn(app, lookup(), message="e o pedido 7?")
    assert response.results[0].status == "needs_information"


def test_money_amounts_are_not_order_numbers(snapshot):
    app = controller(snapshot)
    for message in ("paguei R$ 1,00 no pedido", "paguei 1,00 no pedido"):
        response = turn(app, lookup(1), message=message)
        assert response.results[0].status == "needs_information"


def test_foreign_and_missing_orders_leave_identical_session_state(snapshot):
    states = []
    for number in (3, 999):
        app = controller(snapshot)
        turn(app, lookup(1), message="pedido 1")
        turn(app, lookup(number), message=f"pedido {number}")
        session = app.session
        states.append(
            (
                session.selected_order_id,
                session.pending,
                [m.content.replace(str(number), "N") for m in session.history[-2:]],
            )
        )
    assert states[0] == states[1]


def test_additional_pending_operations_are_announced(snapshot):
    app = controller(snapshot)
    response = turn(app, lookup(), {"type": "payment_options"})
    assert len(app.session.pending) == 2
    assert "Para continuar a consulta do pedido, informe o número do pedido." in (
        response.text
    )
    assert "ainda há 1 consulta(s) aguardando dados" in response.text
    response = update(app, "é o 1", order_id=1)
    assert "Para continuar, informe o produto" in response.text
