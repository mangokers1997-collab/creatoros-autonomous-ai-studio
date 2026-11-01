import unittest
from unittest.mock import patch

from app import channel_orchestrator as orchestrator


class ChannelOrchestratorTests(unittest.TestCase):
    @patch("app.channel_orchestrator.database.publish_job_list", return_value=[
        {"channel_id": "c1", "status": "awaiting_approval"},
        {"channel_id": "c1", "status": "published"},
    ])
    @patch("app.channel_orchestrator.database.project_list", return_value=[
        {"channel_id": "c1", "status": "approved"},
    ])
    @patch("app.channel_orchestrator.database.production_batch_list", return_value=[
        {"strategy_id": "p1", "status": "processing"},
    ])
    @patch("app.channel_orchestrator.database.strategy_plan_get", return_value={
        "items": [{"status": "planned"}, {"status": "approved"}]
    })
    @patch("app.channel_orchestrator.database.strategy_plan_list", return_value=[
        {"id": "p1", "channel_id": "c1", "created_at": "2026-11-01"}
    ])
    @patch("app.channel_orchestrator.database.channel_list", return_value=[
        {"id": "c1", "name": "Finance ID", "platform": "youtube",
         "target_market": "ID", "language": "id", "niche": "finance"}
    ])
    def test_overview_aggregates_channel_workflow(self, *_mocks):
        result = orchestrator.build_channel_orchestrator_overview()
        self.assertEqual(result["channel_count"], 1)
        channel = result["configured_channels"][0]
        self.assertEqual(channel["strategy_count"], 1)
        self.assertEqual(channel["planned_items"], 2)
        self.assertEqual(channel["awaiting_approval"], 1)
        self.assertEqual(channel["published_jobs"], 1)
        self.assertEqual(result["totals"]["active_batches"], 1)

    @patch("app.channel_orchestrator.create_brain_strategy", return_value={
        "id": "new-plan", "name": "Finance ID", "items": [{"id": "i1"}, {"id": "i2"}]
    })
    @patch("app.channel_orchestrator.database.strategy_plan_list", return_value=[
        {"id": "old-plan", "channel_id": "c1", "start_date": "2026-11-01", "days": 30}
    ])
    @patch("app.channel_orchestrator.database.channel_list", return_value=[
        {"id": "c1", "name": "Finance ID", "target_market": "ID",
         "language": "id", "niche": "finance"}
    ])
    def test_strategy_planning_shifts_to_avoid_channel_overlap(self, _channels, _plans, create):
        result = orchestrator.create_multi_channel_strategy_plans(
            ["c1"], "2026-11-01", days=30, videos_per_day=1
        )
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["results"][0]["start_date"], "2026-12-01")
        self.assertEqual(create.call_args.args[4], "2026-12-01")

    @patch("app.channel_orchestrator.database.channel_list", return_value=[])
    def test_rejects_unknown_channel_ids(self, _channels):
        with self.assertRaises(ValueError):
            orchestrator.create_multi_channel_strategy_plans(
                ["missing"], "2026-11-01", days=7, videos_per_day=1
            )

    def test_rejects_duplicate_channel_ids(self):
        with self.assertRaises(ValueError):
            orchestrator.create_multi_channel_strategy_plans(
                ["c1", "c1"], "2026-11-01", days=7, videos_per_day=1
            )


if __name__ == "__main__":
    unittest.main()
