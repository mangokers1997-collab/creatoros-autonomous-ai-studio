import unittest
from unittest.mock import patch

from app.content_brain import build_content_brain_report


class ContentBrainTests(unittest.TestCase):
    @patch("app.content_brain.database.experiment_list", return_value=[])
    @patch("app.content_brain.database.channel_performance_records", return_value=[
        {"views": 1500, "engagement_rate": 4.0, "format": "short", "niche": "finance"}
    ])
    @patch("app.content_brain.database.strategy_plan_list", return_value=[])
    @patch("app.content_brain.database.intelligence_report_list", return_value=[
        {"report_json": '{"recommended_ideas":[{"keyword":"budget planner"}],"keyword_clusters":[{"keyword":"saving","opportunity_score":80}]}'}
    ])
    @patch("app.content_brain.database.trend_items_list", return_value=[
        {"title":"Emergency fund basics", "relevance_score":75, "source":"Google Trends RSS"}
    ])
    @patch("app.content_brain.database.channel_get", return_value=None)
    def test_combines_research_and_trends(self, *_mocks):
        report = build_content_brain_report("ID", "finance", "id")
        topics = {x["topic"] for x in report["recommendations"]}
        self.assertIn("Emergency fund basics", topics)
        self.assertIn("budget planner", topics)
        self.assertIn("saving", topics)
        self.assertEqual(report["evidence"]["published_video_records"], 1)
        self.assertTrue(report["evidence"]["performance_influenced_scoring"])

    @patch("app.content_brain.database.experiment_list", return_value=[])
    @patch("app.content_brain.database.channel_performance_records", return_value=[])
    @patch("app.content_brain.database.strategy_plan_list", return_value=[
        {"id":"plan-1","market":"ID","niche":"finance"}
    ])
    @patch("app.content_brain.database.strategy_plan_get", return_value={
        "items":[{"topic":"Emergency fund basics"}]
    })
    @patch("app.content_brain.database.intelligence_report_list", return_value=[])
    @patch("app.content_brain.database.trend_items_list", return_value=[
        {"title":"Emergency fund basics", "relevance_score":80, "source":"Google Trends RSS"},
        {"title":"Budget planner tips", "relevance_score":60, "source":"Google Trends RSS"}
    ])
    @patch("app.content_brain.database.channel_get", return_value=None)
    def test_excludes_repeated_strategy_topics(self, *_mocks):
        report = build_content_brain_report("ID", "finance", "id")
        topics = [x["topic"] for x in report["recommendations"]]
        self.assertNotIn("Emergency fund basics", topics)
        self.assertIn("Budget planner tips", topics)
        self.assertEqual(report["excluded_duplicates"], ["Emergency fund basics"])

    @patch("app.content_brain.database.channel_get", return_value={"id":"x","target_market":"US"})
    def test_rejects_channel_market_mismatch(self, _mock):
        with self.assertRaises(ValueError):
            build_content_brain_report("ID", "finance", "id", "x")


if __name__ == "__main__":
    unittest.main()
