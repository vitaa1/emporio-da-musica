"""Keep the bundled demonstration usable without the original challenge files."""

import subprocess
import sys
from pathlib import Path

from emporio_da_musica.data import load_snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_demo_integrity_and_synthetic_fields():
    snapshot = load_snapshot(ROOT / "data" / "demo")
    assert [
        len(snapshot.categories),
        len(snapshot.products),
        len(snapshot.customers),
        len(snapshot.orders),
        len(snapshot.order_items),
        len(snapshot.promotions),
    ] == [9, 65, 50, 20, 22, 25]
    for identifier, customer in snapshot.customers.items():
        assert customer.name == f"Demo Customer {identifier}"
        assert customer.phone == "00000000000"
        assert customer.email == f"customer-{identifier}@example.invalid"
        assert customer.city == "Campo Grande"
    for identifier, order in snapshot.orders.items():
        assert order.tracking_code in (None, f"DEMO-ORDER-{identifier}")
        assert order.notes in (None, "Synthetic demonstration note.")


def test_default_command_uses_bundled_data():
    result = subprocess.run(
        [sys.executable, "-m", "emporio_da_musica"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "categories: 9",
        "products: 65",
        "customers: 50",
        "orders: 20",
        "order_items: 22",
        "promotions: 25",
    ]
