"""Run from the repository root: python -m scripts.generate_data."""

import argparse
from pathlib import Path

from flowsense.generator import SEED, generate_data, save_to_sqlite


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/flowsense.sqlite"))
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    data = generate_data(args.seed)
    save_to_sqlite(data, args.output)
    print(f"Saved {len(data):,} observations to {args.output}")


if __name__ == "__main__":
    main()
