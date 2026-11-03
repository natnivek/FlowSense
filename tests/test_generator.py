import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from flowsense.generator import ASSETS, EPISODES, REGIONS, generate_data, save_to_sqlite


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = generate_data()

    def test_dates_and_completeness(self):
        expected = pd.bdate_range("2024-01-01", "2025-12-31").strftime("%Y-%m-%d").tolist()
        self.assertEqual(len(self.data), len(expected) * 9)
        self.assertFalse(self.data.isna().any().any())
        self.assertFalse(self.data.duplicated(["date", "asset_class", "region"]).any())
        self.assertEqual(set(self.data.asset_class), set(ASSETS))
        self.assertEqual(set(self.data.region), set(REGIONS))
        for _, series in self.data.groupby(["asset_class", "region"]):
            self.assertEqual(series.date.tolist(), expected)
            np.testing.assert_allclose(series.cumulative_flow, series.net_flow.cumsum())
        self.assertTrue(np.isfinite(self.data.select_dtypes("number")).all().all())
        self.assertTrue(self.data.positioning_proxy.between(-100, 100).all())

    def test_reproducibility(self):
        pd.testing.assert_frame_equal(self.data, generate_data())
        self.assertFalse(self.data.net_flow.equals(generate_data(43).net_flow))

    def test_time_series_behavior(self):
        correlations = self.data.groupby(["asset_class", "region"]).net_flow.apply(
            lambda series: series.autocorr()
        )
        self.assertTrue((correlations > 0.3).all())
        for start, end, label, _ in EPISODES:
            episode = self.data[self.data.date.between(start, end)]
            self.assertEqual(set(episode.regime), {label})
        means = self.data.groupby(["asset_class", "regime"]).net_flow.mean()
        self.assertGreater(means["equities", "risk_on"], means["equities", "risk_off"])
        self.assertLess(means["government_bonds", "risk_on"], means["government_bonds", "risk_off"])
        volatility = self.data.groupby("regime").volatility_multiplier.mean()
        self.assertGreater(volatility["risk_off"], volatility["neutral"])

    def test_sqlite_schema_roundtrip_and_repeat_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flows.sqlite"
            save_to_sqlite(self.data, path)
            save_to_sqlite(generate_data(), path)
            with sqlite3.connect(path) as connection:
                schema = connection.execute("PRAGMA table_info(flows)").fetchall()
                self.assertEqual([row[1] for row in schema], self.data.columns.tolist())
                self.assertEqual([row[2] for row in schema], ["TEXT"] * 3 + ["REAL"] * 3 + ["TEXT", "REAL"])
                self.assertTrue(all(row[3] == 1 for row in schema))
                self.assertEqual([row[1] for row in schema if row[5]], ["date", "asset_class", "region"])
                restored = pd.read_sql_query("SELECT * FROM flows ORDER BY date, asset_class, region", connection)
                pd.testing.assert_frame_equal(self.data, restored, check_exact=True)
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("INSERT INTO flows SELECT * FROM flows LIMIT 1")


if __name__ == "__main__":
    unittest.main()
