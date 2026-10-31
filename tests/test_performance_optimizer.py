import unittest

from app.performance_optimizer import build_optimization_report


class PerformanceOptimizerTests(unittest.TestCase):
    def test_empty_metrics_returns_data_collection_guidance(self):
        report = build_optimization_report([])
        self.assertEqual(report["status"], "insufficient_data")
        self.assertEqual(report["sample_size"], 0)
        self.assertTrue(report["recommendations"])

    def test_rankings_and_small_sample_caveat(self):
        rows = [
            {"project_id": "1", "title": "Video A", "niche": "finance", "format": "short",
             "views": 1200, "likes": 100, "comments": 10, "shares": 10,
             "watch_time_minutes": 400, "subscribers_gained": 8, "metric_snapshots": 2},
            {"project_id": "2", "title": "Video B", "niche": "finance", "format": "long",
             "views": 600, "likes": 20, "comments": 5, "shares": 5,
             "watch_time_minutes": 500, "subscribers_gained": 2, "metric_snapshots": 1},
            {"project_id": "3", "title": "Video C", "niche": "education", "format": "short",
             "views": 300, "likes": 15, "comments": 3, "shares": 2,
             "watch_time_minutes": 90, "subscribers_gained": 1, "metric_snapshots": 1},
        ]
        report = build_optimization_report(rows)
        self.assertEqual(report["top_videos"][0]["title"], "Video A")
        self.assertEqual(report["sample_size"], 3)
        self.assertEqual(report["status"], "early_signal")
        self.assertTrue(any("sampel" in item["title"].lower() for item in report["recommendations"]))
        self.assertEqual(report["totals"]["engagement_rate"], round(170 / 2100 * 100, 2))

    def test_format_aggregation(self):
        rows = [
            {"title": "A", "niche": "tech", "format": "short", "views": 100,
             "likes": 10, "comments": 0, "shares": 0},
            {"title": "B", "niche": "tech", "format": "short", "views": 300,
             "likes": 20, "comments": 0, "shares": 0},
            {"title": "C", "niche": "tech", "format": "long", "views": 200,
             "likes": 10, "comments": 0, "shares": 0},
        ]
        report = build_optimization_report(rows)
        self.assertEqual(report["format_performance"][0]["label"], "short")
        self.assertEqual(report["format_performance"][0]["average_views"], 200)


if __name__ == "__main__":
    unittest.main()
