import unittest

from indicators import analyze_all_timeframes, analyze_timeframe


def make_candles(values):
    rows = []
    for index, close in enumerate(values):
        rows.append({
            "t": index * 300000,
            "o": close - 0.1,
            "h": close + 0.2,
            "l": close - 0.2,
            "c": close,
            "v": 100.0 + (index % 5),
        })
    return rows


class IndicatorTests(unittest.TestCase):
    def test_uptrend_is_classified_bullish(self):
        result = analyze_timeframe(make_candles([100 + i * 0.2 for i in range(100)]))
        self.assertEqual(result["trend"], "BULLISH")
        self.assertGreater(result["rsi14"], 50)
        self.assertIsNotNone(result["macd_histogram"])

    def test_downtrend_is_classified_bearish(self):
        result = analyze_timeframe(make_candles([120 - i * 0.2 for i in range(100)]))
        self.assertEqual(result["trend"], "BEARISH")
        self.assertLess(result["rsi14"], 50)

    def test_insufficient_history_fails_closed(self):
        with self.assertRaises(ValueError):
            analyze_timeframe(make_candles([100 + i for i in range(20)]))

    def test_aggregate_never_emits_trade_signal_yet(self):
        candles = make_candles([100 + i * 0.2 for i in range(100)])
        data = {tf: {"candles": candles} for tf in ("1d", "4h", "1h", "15m", "5m")}
        result = analyze_all_timeframes(data)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["signal_status"], "TECHNICAL_CONTEXT_ONLY")


if __name__ == "__main__":
    unittest.main()
