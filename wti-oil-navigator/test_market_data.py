import unittest
from unittest.mock import Mock

from market_data import LighterAPIError, LighterPublicAPI


class MarketDiscoveryTests(unittest.TestCase):
    def test_discovers_only_active_wti_perpetual(self):
        api = LighterPublicAPI()
        api.get = Mock(return_value={
            "code": 200,
            "order_books": [
                {"symbol": "WTI", "market_id": 77, "market_type": "perp", "status": "active"},
                {"symbol": "WTI", "market_id": 78, "market_type": "spot", "status": "active"},
                {"symbol": "WTI", "market_id": 79, "market_type": "perp", "status": "inactive"},
            ],
        })
        result = api.discover_wti_perpetual()
        self.assertEqual(result["market_id"], 77)

    def test_refuses_ambiguous_active_markets(self):
        api = LighterPublicAPI()
        api.get = Mock(return_value={
            "code": 200,
            "order_books": [
                {"symbol": "WTI", "market_id": 77, "market_type": "perp", "status": "active"},
                {"symbol": "WTI", "market_id": 80, "market_type": "perp", "status": "active"},
            ],
        })
        with self.assertRaises(LighterAPIError):
            api.discover_wti_perpetual()

    def test_refuses_missing_market(self):
        api = LighterPublicAPI()
        api.get = Mock(return_value={"code": 200, "order_books": []})
        with self.assertRaises(LighterAPIError):
            api.discover_wti_perpetual()


if __name__ == "__main__":
    unittest.main()
