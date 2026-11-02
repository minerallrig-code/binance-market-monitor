import unittest

from backtest import _series, run_backtest


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
