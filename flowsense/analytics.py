"""Descriptive flow analytics using observed columns only."""

from itertools import combinations
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from flowsense.generator import ASSETS, REGIONS


def load_flows(path: str | Path) -> pd.DataFrame:
    """Read an existing database without creating or modifying it."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return pd.read_sql_query(
            "SELECT date, asset_class, region, net_flow, positioning_proxy "
            "FROM flows ORDER BY date, asset_class, region", connection
        )


def _prepare(data: pd.DataFrame) -> pd.DataFrame:
    columns = ["date", "asset_class", "region", "net_flow", "positioning_proxy"]
    missing = set(columns) - set(data.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    result = data[columns].copy()
    if result.empty or result.isna().any().any():
        raise ValueError("Input must be nonempty and have no missing values")
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    if (result.date != result.date.dt.normalize()).any() or (result.date.dt.dayofweek > 4).any():
        raise ValueError("Dates must be business-day dates without time components")
    if result.duplicated(["date", "asset_class", "region"]).any():
        raise ValueError("Duplicate date/asset/region keys")
    if not result.asset_class.isin(ASSETS).all() or not result.region.isin(REGIONS).all():
        raise ValueError("Unknown asset class or region")
    for column in ("net_flow", "positioning_proxy"):
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
        if not np.isfinite(result[column]).all():
            raise ValueError(f"Nonfinite {column}")
    if not result.positioning_proxy.between(-100, 100).all():
        raise ValueError("Positioning proxy must be between -100 and 100")
    result = result.sort_values(["date", "asset_class", "region"], ignore_index=True)
    expected = pd.bdate_range(result.date.min(), result.date.max())
    for _, series in result.groupby(["asset_class", "region"]):
        if not pd.DatetimeIndex(series.date).equals(expected):
            raise ValueError("Every series must cover the same complete weekday calendar")
    return result


def calculate_metrics(
    data: pd.DataFrame, window: int = 20, position_lag: int = 5
) -> pd.DataFrame:
    """Calculate per-series metrics; warm-up and zero-variance z-scores are NaN."""
    if isinstance(window, bool) or not isinstance(window, int) or window < 2:
        raise ValueError("window must be an integer >= 2")
    if isinstance(position_lag, bool) or not isinstance(position_lag, int) or position_lag < 1:
        raise ValueError("position_lag must be a positive integer")
    frame = _prepare(data)
    results = []
    for _, series in frame.groupby(["asset_class", "region"], sort=True):
        series = series.copy()
        flow = series.net_flow
        prior = flow.shift(1).rolling(window, min_periods=window)
        series["prior_flow_mean"] = prior.mean()
        series["prior_flow_std"] = prior.std(ddof=1)
        denominator = series.prior_flow_std.replace(0, np.nan)
        series["flow_zscore"] = (flow - series.prior_flow_mean) / denominator
        series["cumulative_flow"] = flow.cumsum()
        series["rolling_net_flow"] = flow.rolling(window, min_periods=window).sum()
        series["position_change_1d"] = series.positioning_proxy.diff()
        series["position_change"] = series.positioning_proxy.diff(position_lag)
        results.append(series)
    output = pd.concat(results).sort_values(["date", "asset_class", "region"], ignore_index=True)
    output["window"] = window
    output["position_lag"] = position_lag
    return output


def calculate_divergences(metrics: pd.DataFrame) -> pd.DataFrame:
    """Compare every available asset pair within a region on matched dates."""
    columns = ["date", "region", "asset_a", "asset_b", "zscore_a", "zscore_b",
               "zscore_spread", "opposite_flow_direction"]
    rows = []
    for region, regional in metrics.groupby("region", sort=True):
        available = [asset for asset in ASSETS if asset in set(regional.asset_class)]
        for asset_a, asset_b in combinations(available, 2):
            left = regional[regional.asset_class == asset_a]
            right = regional[regional.asset_class == asset_b]
            pair = left.merge(right, on="date", suffixes=("_a", "_b"), validate="one_to_one")
            rows.append(pd.DataFrame({
                "date": pair.date, "region": region,
                "asset_a": asset_a, "asset_b": asset_b,
                "zscore_a": pair.flow_zscore_a, "zscore_b": pair.flow_zscore_b,
                "zscore_spread": pair.flow_zscore_a - pair.flow_zscore_b,
                "opposite_flow_direction": (
                    ((pair.net_flow_a > 0) & (pair.net_flow_b < 0))
                    | ((pair.net_flow_a < 0) & (pair.net_flow_b > 0))
                ),
            }))
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns].sort_values(
        ["date", "region", "asset_a", "asset_b"], ignore_index=True
    )
