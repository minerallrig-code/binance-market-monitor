import unittest
from datetime import datetime, timezone

from event_study import analyze_news_response


class EventStudyTests(unittest.TestCase):
    def test_links_headline_to_forward_price_returns(self):
        start = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            {"t": start + i * 900000, "o": 100 + i * 0.01, "h": 101 + i * 0.01,
             "l": 99 + i * 0.01, "c": 100 + i * 0.01, "v": 100}
            for i in range(200)
        ]
        news = {
            "items": [{
                "id": "abc",
                "title": "OPEC announces production change",
                "publisher": "Reuters",
                "published_at": datetime.fromtimestamp((start + 900000) / 1000, timezone.utc).isoformat(),
                "topics": ["opec", "production"],
                "publisher_trusted_list_match": True,
            }]
        }
        result = analyze_news_response(news, candles)
        self.assertEqual(result["events_matched"], 1)
        self.assertIn("opec", result["topics"])
        self.assertIn("1h", result["topics"]["opec"]["forward_returns"])
        self.assertIn("period_baseline_non_overlapping", result)
        self.assertIn("excess_mean_vs_period_baseline_pct", result["topics"]["opec"]["forward_returns"]["1h"])
        self.assertIn("causation", result["warning"])

    def test_rejects_insufficient_history(self):
        result = analyze_news_response({"items": []}, [{"t": i, "c": 100} for i in range(10)])
        self.assertEqual(result["status"], "INSUFFICIENT_PRICE_HISTORY")


if __name__ == "__main__":
    unittest.main()
