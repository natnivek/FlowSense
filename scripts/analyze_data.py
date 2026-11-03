"""Compute analytics and export CSVs without modifying the source database."""

import argparse
from pathlib import Path

from flowsense.analytics import calculate_divergences, calculate_metrics, load_flows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/flowsense.sqlite"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analytics"))
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--position-lag", type=int, default=5)
    args = parser.parse_args()
    metrics = calculate_metrics(load_flows(args.database), args.window, args.position_lag)
    divergences = calculate_divergences(metrics)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.output_dir / "flow_metrics.csv", index=False, date_format="%Y-%m-%d")
    divergences.to_csv(args.output_dir / "cross_asset_divergences.csv", index=False, date_format="%Y-%m-%d")
    print(f"Saved {len(metrics):,} metric rows and {len(divergences):,} asset-pair rows to {args.output_dir}")
    latest = metrics[metrics.date == metrics.date.max()]
    print(latest[["date", "asset_class", "region", "flow_zscore", "position_change"]].to_string(index=False))


if __name__ == "__main__":
    main()
