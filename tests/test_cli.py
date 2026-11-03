"""Offline command usage, input limits, and CLI lifecycle."""

from io import StringIO

import pytest

from emporio_da_musica.cli import run_cli
from emporio_da_musica.providers.demo import DemoProvider


def test_demo_cli_multiple_messages_and_oversized_line(app):
    app.provider = DemoProvider()
    source = StringIO("x" * 9000 + "\n/buscar Violão\n/preco 2 1 pix\n/sair\n")
    output = StringIO()
    run_cli(app, source, output)
    text = output.getvalue()
    assert "Mensagem muito longa" in text
    assert "R$ 1.900,00" in text
    assert text.endswith("Até mais!\n")


def test_cli_eof_and_interrupt(app):
    output = StringIO()
    run_cli(app, StringIO(""), output)
    assert output.getvalue().endswith("Até mais!\n")

    class Interrupted:
        def readline(self, size):
            raise KeyboardInterrupt

    output = StringIO()
    run_cli(app, Interrupted(), output)
    assert output.getvalue().endswith("Até mais!\n")


def test_cli_module_can_run_as_documented():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica.cli", "--demo"],
        input="/buscar Yamaha\n/preco 1 1 pix\n/sair\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Yamaha" in result.stdout and "Desconto PIX" in result.stdout
    assert "Até mais!" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command,example",
    [
        ("/preco", "/preco 1 1 pix"),
        ("/escolher", "/escolher 1"),
        ("/quantidade", "/quantidade 1"),
        ("/pagamento", "/pagamento pix"),
    ],
)
def test_demo_missing_arguments_show_usage_without_provider_error(
    app, caplog, command, example
):
    app.provider = DemoProvider()
    output = StringIO()
    run_cli(app, StringIO(command + "\n/sair\n"), output)
    assert example in output.getvalue()
    assert "Não consegui interpretar" not in output.getvalue()
    assert "Extraction failed" not in caplog.text


@pytest.mark.parametrize("command", ["/escolher 1", "/quantidade 1", "/pagamento pix"])
def test_demo_update_without_pending_explains_next_step(app, caplog, command):
    app.provider = DemoProvider()
    output = StringIO()
    run_cli(app, StringIO(command + "\n/sair\n"), output)
    assert "Não há consulta pendente" in output.getvalue()
    assert not caplog.records
    assert not app.session.history


def test_demo_usage_error_preserves_pending_and_valid_selection_still_works(
    app, caplog
):
    app.provider = DemoProvider()
    output = StringIO()
    run_cli(
        app,
        StringIO(
            "/buscar Violão\n/preco 9 1 pix\n/escolher\n/quantidade 2\n/escolher 2\n/sair\n"
        ),
        output,
    )
    assert "Use /escolher POSICAO" in output.getvalue()
    assert "Esse dado não foi solicitado" in output.getvalue()
    assert "R$ 1.900,00" in output.getvalue()
    assert not app.session.pending
    assert not caplog.records


def test_demo_commands_accept_every_method():
    from datetime import datetime, timezone
    from pathlib import Path

    from emporio_da_musica.controller import Controller
    from emporio_da_musica.data.loader import load_snapshot
    from emporio_da_musica.providers.demo import DemoProvider

    for method in ("pix", "debit", "credit", "boleto"):
        app = Controller(
            load_snapshot(Path(__file__).resolve().parents[1] / "data/demo"),
            DemoProvider(),
            clock=lambda: datetime.now(timezone.utc),
        )
        app.handle("/buscar Takamine GD20")
        response = app.handle(f"/preco 1 1 {method}")
        assert response.results[-1].data.payment_method == method
