import unittest

from app.intelligence_engine import _keyword_clusters, _tokens, COUNTRY_LANGUAGE
from app.trend_engine import MARKETS, _traffic_score, _score


class TrendScoringTests(unittest.TestCase):
    def test_supported_markets_include_target_regions(self):
        for market in ("US", "GB", "CA", "AU", "JP", "AE", "ID"):
            self.assertIn(market, MARKETS)

    def test_traffic_labels_are_approximate_ordered_signals(self):
        self.assertGreater(_traffic_score("100000+"), _traffic_score("1000+"))
        self.assertEqual(_traffic_score(""), 10.0)

    def test_keyword_relevance_uses_niche_and_seed_terms(self):
        score = _score("Personal finance tips for beginners", "5000+", "personal finance", ["beginners"])
        self.assertGreater(score, _score("Weather update", "5000+", "personal finance", []))


class KeywordAnalysisTests(unittest.TestCase):
    def test_stopwords_are_removed(self):
        self.assertEqual(_tokens("the best tips for saving money"), ["saving", "money"])

    def test_clusters_rank_repeated_trend_terms(self):
        clusters = _keyword_clusters(
            ["budgeting", "saving money"],
            ["Budgeting tips for beginners", "Budgeting mistakes", "Saving money every month"],
        )
        by_keyword = {row["keyword"]: row for row in clusters}
        self.assertGreater(by_keyword["budgeting"]["trend_mentions"], 1)
        self.assertGreater(by_keyword["budgeting"]["opportunity_score"], 0)

    def test_market_language_defaults_are_available(self):
        self.assertEqual(COUNTRY_LANGUAGE["JP"], "ja")
        self.assertEqual(COUNTRY_LANGUAGE["AE"], "ar")


if __name__ == "__main__":
    unittest.main()
