import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from flowsense.analytics import calculate_divergences, calculate_metrics, load_flows
from flowsense.generator import generate_data, save_to_sqlite


def fixture():
    dates = pd.bdate_range("2025-01-01", periods=6)
    return pd.DataFrame({
        "date": dates, "asset_class": "equities", "region": "US",
        "net_flow": [1, 2, 3, 4, 5, 6], "positioning_proxy": [0, 2, 5, 9, 14, 20],
    })


class AnalyticsTests(unittest.TestCase):
    def test_known_calculations_and_warmup(self):
        metrics = calculate_metrics(fixture(), window=3, position_lag=2)
        self.assertTrue(metrics.flow_zscore.iloc[:3].isna().all())
        np.testing.assert_allclose(metrics.flow_zscore.iloc[3:], [2, 2, 2])
        np.testing.assert_allclose(metrics.prior_flow_mean.iloc[3:], [2, 3, 4])
        np.testing.assert_allclose(metrics.prior_flow_std.iloc[3:], [1, 1, 1])
        np.testing.assert_allclose(metrics.cumulative_flow, [1, 3, 6, 10, 15, 21])
        np.testing.assert_allclose(metrics.rolling_net_flow.iloc[2:], [6, 9, 12, 15])
        np.testing.assert_allclose(metrics.position_change.iloc[2:], [5, 7, 9, 11])
        np.testing.assert_allclose(metrics.position_change_1d.iloc[1:], [2, 3, 4, 5, 6])

    def test_no_future_leakage_and_current_excluded_from_baseline(self):
        original = fixture()
        before = calculate_metrics(original, 3, 2)
        changed = original.copy()
        changed.loc[5, ["net_flow", "positioning_proxy"]] = [1000, -90]
        after = calculate_metrics(changed, 3, 2)
        pd.testing.assert_frame_equal(before.iloc[:5], after.iloc[:5])
        self.assertEqual(after.prior_flow_mean.iloc[5], 4)
        self.assertEqual(after.prior_flow_std.iloc[5], 1)
        self.assertEqual(after.flow_zscore.iloc[5], 996)

    def test_zero_variance_and_short_history(self):
        data = fixture()
        data["net_flow"] = 1
        self.assertTrue(calculate_metrics(data, 3).flow_zscore.isna().all())
        data.loc[5, "net_flow"] = 10
        self.assertTrue(np.isnan(calculate_metrics(data, 3).flow_zscore.iloc[5]))
        self.assertTrue(calculate_metrics(data, 20).flow_zscore.isna().all())

    def test_group_isolation_sorting_and_no_mutation(self):
        first = fixture()
        second = fixture().assign(region="Asia", net_flow=lambda d: d.net_flow * 10)
        data = pd.concat([first, second]).sample(frac=1, random_state=1)
        snapshot = data.copy(deep=True)
        metrics = calculate_metrics(data, 3, 2)
        pd.testing.assert_frame_equal(data, snapshot)
        for region in ("US", "Asia"):
            np.testing.assert_allclose(metrics[metrics.region == region].flow_zscore.iloc[3:], [2, 2, 2])

    def test_divergence_sign_and_zero_flow(self):
        equities = fixture()
        bonds = fixture().assign(asset_class="government_bonds", net_flow=lambda d: -d.net_flow)
        metrics = calculate_metrics(pd.concat([equities, bonds]), 3, 2)
        pairs = calculate_divergences(metrics)
        self.assertEqual(len(pairs), 6)
        self.assertTrue(pairs.zscore_spread.iloc[:3].isna().all())
        np.testing.assert_allclose(pairs.zscore_spread.iloc[3:], [4, 4, 4])
        self.assertTrue(pairs.opposite_flow_direction.all())
        metrics.loc[metrics.date == metrics.date.min(), "net_flow"] = 0
        self.assertFalse(calculate_divergences(metrics).opposite_flow_direction.iloc[0])
        self.assertTrue(calculate_divergences(calculate_metrics(equities, 3)).empty)

    def test_invalid_inputs(self):
        cases = [fixture().drop(columns="net_flow"), fixture().iloc[:0],
                 pd.concat([fixture(), fixture().iloc[:1]]), fixture().drop(index=2),
                 fixture().assign(region="unknown"), fixture().assign(positioning_proxy=101),
                 fixture().assign(net_flow=np.inf), fixture().assign(net_flow=np.nan)]
        weekend = fixture()
        weekend.loc[0, "date"] = pd.Timestamp("2025-01-04")
        cases.append(weekend)
        for case in cases:
            with self.subTest(case=case.shape), self.assertRaises(ValueError):
                calculate_metrics(case)
        for window, lag in [(1, 5), (2, 0), (2.5, 5), (True, 5)]:
            with self.assertRaises(ValueError):
                calculate_metrics(fixture(), window, lag)

    def test_database_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                load_flows(path)
            self.assertFalse(path.exists())
            source = generate_data()
            save_to_sqlite(source, path)
            original_bytes = path.read_bytes()
            metrics = calculate_metrics(load_flows(path))
            pairs = calculate_divergences(metrics)
            self.assertEqual(len(metrics), 4707)
            self.assertEqual(len(pairs), 4707)
            self.assertEqual(metrics.flow_zscore.isna().sum(), 20 * 9)
            self.assertEqual(metrics.position_change.isna().sum(), 5 * 9)
            self.assertNotIn("regime", metrics)
            self.assertNotIn("volatility_multiplier", metrics)
            np.testing.assert_allclose(metrics.cumulative_flow, source.cumulative_flow)
            numeric = metrics.select_dtypes("number")
            self.assertFalse(np.isinf(numeric).any().any())
            self.assertEqual(original_bytes, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
