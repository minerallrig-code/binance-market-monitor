import unittest

from backtest import _funding_cost_fraction, _series, run_backtest
from market_data import LighterAPIError
from run_backtest import fetch_funding_history


def candles(start_ms, step_ms, values):
    return [
        {
            "t": start_ms + i * step_ms,
            "o": value - 0.05,
            "h": value + 0.15,
            "l": value - 0.15,
            "c": value,
            "v": 100.0 + (i % 7),
        }
        for i, value in enumerate(values)
    ]


class BacktestTests(unittest.TestCase):
    def test_macd_histogram_warms_up_instead_of_nan_forever(self):
        values = [100 + i * 0.1 for i in range(100)]
        result = _series(candles(0, 900000, values))
        self.assertTrue(any(value is not None for value in result["hist"]))
        self.assertIsNotNone(result["hist"][-1])

    def test_longs_pay_when_lighter_direction_is_long(self):
        records = [{"timestamp": 3600, "rate": "0.0004", "direction": "long"}]
        cost, count = _funding_cost_fraction("LONG", 0, 7200000, records)
        self.assertAlmostEqual(cost, 0.000004)
        self.assertEqual(count, 1)

    def test_shorts_receive_when_lighter_direction_is_long(self):
        records = [{"timestamp": 3600, "rate": "0.0004", "direction": "long"}]
        cost, count = _funding_cost_fraction("SHORT", 0, 7200000, records)
        self.assertAlmostEqual(cost, -0.000004)
        self.assertEqual(count, 1)

    def test_unknown_funding_direction_fails_closed(self):
        records = [{"timestamp": 3600, "rate": "0.0004", "direction": "unknown"}]
        with self.assertRaises(ValueError):
            _funding_cost_fraction("LONG", 0, 7200000, records)

    def test_funding_history_falls_back_to_daily_windows(self):
        class FakeAPI:
            def funding_history(self, market_id, start, end):
                if end - start > 24 * 3600:
                    raise LighterAPIError("HTTP Error 400: Bad Request")
                return [{"timestamp": start + 3600, "rate": "0.0004", "direction": "long"}]

        rows, skipped = fetch_funding_history(FakeAPI(), 145, 0, 7 * 24 * 3600)
        self.assertEqual(len(rows), 7)
        self.assertEqual(skipped, [])

    def test_insufficient_history_is_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(
                candles(0, 900000, [100 + i for i in range(30)]),
                candles(0, 3600000, [100 + i for i in range(30)]),
                candles(0, 14400000, [100 + i for i in range(30)]),
            )

    def test_replay_reports_assumptions_and_no_lookahead_entry(self):
        # Smooth trend data intentionally produces no RSI pullback recovery signal.
        base = candles(0, 900000, [100 + i * 0.05 for i in range(180)])
        hourly = candles(0, 3600000, [100 + i * 0.2 for i in range(180)])
        four_hour = candles(0, 14400000, [100 + i * 0.3 for i in range(180)])
        result = run_backtest(base, hourly, four_hour)
        self.assertIn(result["status"], ("NO_TRADES", "RESEARCH_ONLY"))
        self.assertIn("next 15m candle open", result["assumptions"]["entry"])
        self.assertEqual(result["assumptions"]["same_bar_stop_target"], "stop first (conservative)")


if __name__ == "__main__":
    unittest.main()
