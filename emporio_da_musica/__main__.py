"""Validate a source directory and print non-sensitive table counts."""

import argparse
from pathlib import Path

from .data import DataError, load_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_dir",
        nargs="?",
        default=Path(__file__).resolve().parent.parent / "data" / "demo",
        help="CSV directory (default: the bundled data/demo snapshot)",
    )
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.data_dir)
    except DataError as error:
        parser.exit(1, f"Data validation failed: {error}\n")
    for table in (
        "categories",
        "products",
        "customers",
        "orders",
        "order_items",
        "promotions",
    ):
        print(f"{table}: {len(getattr(snapshot, table))}")


if __name__ == "__main__":
    main()
