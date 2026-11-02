import unittest

from news_ingest import _topics, _parse_time


class NewsTagTests(unittest.TestCase):
    def test_classifies_oil_market_topics(self):
        tags = _topics("OPEC+ production targets and tanker risk in the Strait of Hormuz")
        self.assertIn("opec", tags)
        self.assertIn("shipping", tags)
        self.assertIn("production", tags)

    def test_does_not_infer_direction(self):
        tags = _topics("Iran talks and falling crude inventories")
        self.assertIn("geopolitics", tags)
        self.assertIn("inventories", tags)
        self.assertNotIn("bullish", tags)
        self.assertNotIn("bearish", tags)

    def test_parses_rfc822_timestamp(self):
        self.assertTrue(_parse_time("Mon, 02 Nov 2026 09:00:00 GMT").startswith("2026-11-02T09:00:00"))


if __name__ == "__main__":
    unittest.main()
