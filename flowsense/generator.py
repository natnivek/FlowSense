"""Deterministic synthetic flows; no external market data is used."""

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd


SEED = 42
ASSETS = ("equities", "government_bonds", "fx")
REGIONS = ("US", "Europe", "Asia")
EPISODES = (
    ("2024-03-04", "2024-04-12", "risk_on", 1.0),
    ("2024-08-05", "2024-09-13", "risk_off", -1.0),
    ("2025-02-03", "2025-03-14", "risk_on", 1.0),
    ("2025-09-01", "2025-10-10", "risk_off", -1.0),
)


def generate_data(seed: int = SEED) -> pd.DataFrame:
    """Generate all nine series over the fixed 2024–2025 business calendar."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", "2025-12-31")
    n = len(dates)
    regime = np.full(n, "neutral", dtype=object)
    sentiment = np.zeros(n)
    for start, end, label, direction in EPISODES:
        mask = (dates >= start) & (dates <= end)
        regime[mask], sentiment[mask] = label, direction

    # Persistent log volatility, with additional uncertainty in risk-off windows.
    log_vol = np.zeros(n)
    for t in range(1, n):
        log_vol[t] = 0.96 * log_vol[t - 1] + rng.normal(0, 0.10)
    volatility = np.exp(log_vol) * np.where(sentiment < 0, 1.8, 1.0)
    common_shock = rng.normal(size=n)
    rows = []
    for asset, scale, loading in zip(ASSETS, (110.0, 85.0, 65.0), (1.0, -0.8, 0.5)):
        asset_shock = rng.normal(size=n)
        for region, region_scale in zip(REGIONS, (1.2, 1.0, 0.8)):
            noise = (0.45 * common_shock + 0.45 * asset_shock
                     + np.sqrt(1 - 2 * 0.45**2) * rng.normal(size=n))
            flow = np.zeros(n)
            position = np.zeros(n)
            for t in range(n):
                previous_flow = flow[t - 1] if t else 0.0
                target = 1.5 * loading * sentiment[t] * scale * region_scale
                flow[t] = (0.60 * previous_flow + 0.40 * target
                           + scale * region_scale * volatility[t] * noise[t])
                previous_position = position[t - 1] if t else 0.0
                position[t] = 0.97 * previous_position + 0.03 * flow[t] / (scale * region_scale)
            rows.append(pd.DataFrame({
                "date": dates.strftime("%Y-%m-%d"),
                "asset_class": asset,
                "region": region,
                "net_flow": flow,
                "cumulative_flow": np.cumsum(flow),
                "positioning_proxy": 100 * np.tanh(position),
                "regime": regime,
                "volatility_multiplier": volatility,
            }))
    return pd.concat(rows, ignore_index=True).sort_values(
        ["date", "asset_class", "region"], ignore_index=True
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS flows (
    date TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK(asset_class IN ('equities', 'government_bonds', 'fx')),
    region TEXT NOT NULL CHECK(region IN ('US', 'Europe', 'Asia')),
    net_flow REAL NOT NULL,
    cumulative_flow REAL NOT NULL,
    positioning_proxy REAL NOT NULL CHECK(positioning_proxy BETWEEN -100 AND 100),
    regime TEXT NOT NULL CHECK(regime IN ('neutral', 'risk_on', 'risk_off')),
    volatility_multiplier REAL NOT NULL CHECK(volatility_multiplier > 0),
    PRIMARY KEY (date, asset_class, region)
);
"""


def save_to_sqlite(data: pd.DataFrame, path: str | Path) -> None:
    """Atomically replace this application's table while retaining other tables."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(SCHEMA)
        connection.execute("DELETE FROM flows")
        placeholders = ", ".join("?" for _ in data.columns)
        columns = ", ".join(data.columns)
        connection.executemany(
            f"INSERT INTO flows ({columns}) VALUES ({placeholders})",
            data.itertuples(index=False, name=None),
        )
