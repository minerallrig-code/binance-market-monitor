import unittest

import bybit_monitor
from multi_asset_backtest import snapshot


class SnapshotParityTests(unittest.TestCase):
    def test_fast_historical_snapshot_matches_live_analyzer(self):
        rows = []
        price = 100.0
        for i in range(180):
            price += ((i % 9) - 4) * 0.17 + 0.03
            rows.append({
                "time": i * 300_000,
                "close_time": (i + 1) * 300_000 - 1,
                "open": price - 0.1,
                "high": price + 0.7 + (i % 3) * 0.05,
                "low": price - 0.6,
                "close": price,
                "volume": 1000.0 + (i % 13) * 31.0,
            })
        expected = bybit_monitor.analyze(rows)
        actual = snapshot(rows)
        for key in ("close", "ema20", "ema50", "rsi14", "rsi6", "volume_ratio_20", "false_breakout"):
            self.assertAlmostEqual(actual[key], expected[key], places=9) if isinstance(actual[key], float) else self.assertEqual(actual[key], expected[key])
        self.assertAlmostEqual(actual["macd"]["histogram"], expected["macd"]["histogram"], places=9)
        self.assertEqual(actual["macd"]["histogram_rising"], expected["macd"]["histogram_rising"])


if __name__ == "__main__":
    unittest.main()
