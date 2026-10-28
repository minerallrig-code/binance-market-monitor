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


if __name__ == "__main__":
    unittest.main()
