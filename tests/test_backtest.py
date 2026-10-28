import unittest

import backtest


def candle(t, o, h, l, c):
    return {"time": t, "close_time": t + 3_599_999,
            "open": o, "high": h, "low": l, "close": c,
            "volume": 1.0, "turnover": c}


class BacktestTests(unittest.TestCase):
    def test_atr_uses_true_range(self):
        rows = [candle(i * 3_600_000, 100, 102, 99, 101) for i in range(20)]
        self.assertAlmostEqual(backtest.atr(rows, 14), 3.0)

    def test_atr_needs_previous_close(self):
        self.assertIsNone(backtest.atr([candle(0, 100, 101, 99, 100)], 14))

    def test_summary_subtracts_costs_and_counts_win_rate(self):
        trades = [
            {"net_pnl_usdc": 0.02, "gross_pnl_usdc": 0.04,
             "fees_usdc": 0.01, "funding_usdc": 0.01},
            {"net_pnl_usdc": -0.03, "gross_pnl_usdc": -0.01,
             "fees_usdc": 0.01, "funding_usdc": 0.01},
        ]
        result = backtest.summarize(trades, 30, {"1h": 100, "15m": 400, "5m": 1200})
        self.assertEqual(result["trades"], 2)
        self.assertEqual(result["win_rate_pct"], 50.0)
        self.assertAlmostEqual(result["net_pnl_usdc"], -0.01)
        self.assertAlmostEqual(result["fees_usdc"], 0.02)
        self.assertAlmostEqual(result["funding_usdc"], 0.02)


if __name__ == "__main__":
    unittest.main()
