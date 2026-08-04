import unittest

from pipeline.demo_keyword_scoring import deduplicate_channels, keyword_metrics
from pipeline.demo_keyword_search import collect_domain


class DemoKeywordTests(unittest.TestCase):
    def test_deduplicates_channels(self):
        self.assertEqual(1, len(deduplicate_channels([{"channel_id": "a"}, {"channel_id": "a"}])))

    def test_keyword_score_is_bounded(self):
        result = keyword_metrics({"title": "SPF sunscreen", "videos": [{"title": "sunblock SPF"}]},
                                 ["sunscreen", "sunblock", "SPF"])
        self.assertGreater(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_search_limits_and_quota_without_network(self):
        def fake(endpoint, _key, params):
            if endpoint == "search":
                return {"items": [{"snippet": {"channelId": "UC" + str(i).zfill(22)}} for i in range(5)]}
            if endpoint == "channels":
                return {"items": []}
            raise AssertionError(endpoint)
        result = collect_domain("sunscreen", "unused", fake)
        self.assertEqual(6, result["apiUsage"]["calls"]["search.list"])
        self.assertEqual(601, result["apiUsage"]["estimatedQuotaUnits"])


if __name__ == "__main__":
    unittest.main()
