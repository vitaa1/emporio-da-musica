"""Deterministic response rendering and terminal text safety."""

from dataclasses import replace

from .support import search, turn


def test_terminal_control_sequences_are_not_rendered(app):
    app.snapshot.products[30] = replace(
        app.snapshot.products[30], name="Piano\x1b[2J\nFake"
    )
    response = turn(app, search("Piano"))
    assert "\x1b" not in response.text and "\nFake" not in response.text
