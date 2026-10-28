import unittest

import bybit_monitor


class BtcFilterTests(unittest.TestCase):
    def test_btc_symbol_does_not_require_self_filter(self):
        self.assertTrue(bybit_monitor.btc_filter_passes("BTCUSDT", {}))

    def test_altcoin_is_blocked_when_btc_data_missing(self):
        self.assertFalse(bybit_monitor.btc_filter_passes("ETHUSDT", {}))
        self.assertFalse(bybit_monitor.btc_filter_passes("SOLUSDT", {"1h": {"error": "unavailable"}}))

    def test_altcoin_is_blocked_when_btc_trend_is_bearish(self):
        btc = {"1h": {"ema20": 98.0, "ema50": 100.0, "close": 97.0}}
        self.assertFalse(bybit_monitor.btc_filter_passes("ETHUSDT", btc))

    def test_altcoin_allowed_when_btc_trend_is_not_bearish(self):
        btc = {"1h": {"ema20": 102.0, "ema50": 100.0, "close": 103.0}}
        self.assertTrue(bybit_monitor.btc_filter_passes("SOLUSDT", btc))

    def test_altcoin_blocked_when_btc_indicators_are_incomplete(self):
        btc = {"1h": {"ema20": 102.0, "ema50": None, "close": 103.0}}
        self.assertFalse(bybit_monitor.btc_filter_passes("SOLUSDT", btc))


class SignalClassifierTests(unittest.TestCase):
    def valid_item(self):
        return {
            "1h": {"ema20": 105.0, "ema50": 100.0, "close": 106.0},
            "15m": {"ema20": 104.0, "close": 106.0, "rsi14": 60.0,
                    "macd": {"histogram": 1.0}, "volume_ratio_20": 1.2,
                    "false_breakout": False},
            "5m": {"ema20": 105.0, "close": 106.0, "rsi6": 58.0,
                   "macd": {"histogram_rising": True}},
        }

    def test_btc_long_when_all_filters_pass(self):
        self.assertEqual(bybit_monitor.classify_symbol("BTCUSDT", self.valid_item()), "LONG")

    def test_eth_long_requires_non_bearish_btc(self):
        btc = {"1h": {"ema20": 105.0, "ema50": 100.0, "close": 106.0}}
        self.assertEqual(bybit_monitor.classify_symbol("ETHUSDT", self.valid_item(), btc), "LONG")
        bearish = {"1h": {"ema20": 98.0, "ema50": 100.0, "close": 97.0}}
        self.assertEqual(bybit_monitor.classify_symbol("ETHUSDT", self.valid_item(), bearish), "WAIT")

    def test_false_breakout_blocks_long(self):
        item = self.valid_item()
        item["15m"]["false_breakout"] = True
        self.assertEqual(bybit_monitor.classify_symbol("BTCUSDT", item), "WAIT")

    def test_missing_required_indicator_is_unavailable(self):
        item = self.valid_item()
        item["15m"]["macd"] = None
        self.assertEqual(bybit_monitor.classify_symbol("BTCUSDT", item), "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
