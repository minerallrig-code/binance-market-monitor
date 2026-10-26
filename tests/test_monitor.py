import unittest
from datetime import datetime, timezone

import monitor


def candles_from_closes(closes, volumes=None):
    volumes = volumes or [100.0] * len(closes)
    rows = []
    for i, (close, volume) in enumerate(zip(closes, volumes)):
        rows.append({
            "time": 1_700_000_000_000 + i * 60_000,
            "close_time": 1_700_000_000_000 + (i + 1) * 60_000 - 1,
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": volume, "turnover": close * volume,
        })
    return rows


class IndicatorTests(unittest.TestCase):
    def test_ema_returns_none_when_history_too_short(self):
        self.assertIsNone(monitor.ema([1.0, 2.0], 3))

    def test_ema_matches_constant_series(self):
        self.assertAlmostEqual(monitor.ema([10.0] * 60, 20), 10.0)

    def test_rsi_up_only_is_100(self):
        self.assertEqual(monitor.rsi(list(range(1, 40)), 6), 100.0)

    def test_rsi_down_only_is_zero(self):
        self.assertEqual(monitor.rsi(list(range(40, 1, -1)), 6), 0.0)

    def test_macd_histogram_rising_flag(self):
        result = monitor.macd([100 + i * 0.5 for i in range(100)])
        self.assertIsNotNone(result)
        self.assertIn("histogram_rising", result)

    def test_volume_baseline_excludes_latest_candle(self):
        rows = candles_from_closes([100.0] * 70, [100.0] * 69 + [300.0])
        result = monitor.analyze(rows)
        self.assertAlmostEqual(result["volume_ma5"], 100.0)
        self.assertAlmostEqual(result["volume_ma10"], 100.0)
        self.assertAlmostEqual(result["volume_vs_ma5"], 3.0)
        self.assertAlmostEqual(result["volume_vs_ma10"], 3.0)

    def test_insufficient_candles_fail_closed(self):
        with self.assertRaises(ValueError):
            monitor.analyze(candles_from_closes([100.0] * 59))

    def test_classifier_returns_wait_for_mixed_conditions(self):
        rows = candles_from_closes([100.0] * 80)
        data = {tf: monitor.analyze(rows) for tf in ("1h", "15m", "5m")}
        result = monitor.classify_long(data)
        self.assertEqual(result["signal"], "WAIT")


if __name__ == "__main__":
    unittest.main()
