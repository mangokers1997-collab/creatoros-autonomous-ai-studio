import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.path_patcher = patch.object(database, "DB_PATH", self.db_path)
        self.path_patcher.start()
        database.init_db()

    def tearDown(self):
        self.path_patcher.stop()
        self.temp_dir.cleanup()

    def test_channel_and_project_persist(self):
        channel = database.channel_create({
            "name": "Test channel", "platform": "youtube",
            "target_market": "US", "language": "en", "niche": "education"
        })
        self.assertEqual(len(database.channel_list()), 1)

        project = database.project_create({
            "title": "Test video", "niche": "education",
            "target_market": "US", "language": "en",
            "format": "short", "channel_id": channel["id"], "brief": "A test"
        })
        self.assertEqual(database.project_get(project["id"])["status"], "idea")
        updated = database.project_update_status(project["id"], "research")
        self.assertEqual(updated["status"], "research")
        self.assertEqual(len(database.project_list(status="research")), 1)

    def test_deleting_channel_keeps_project_unassigned(self):
        channel = database.channel_create({
            "name": "Test channel", "platform": "youtube",
            "target_market": "US", "language": "en", "niche": "education"
        })
        project = database.project_create({
            "title": "Test video", "niche": "education",
            "target_market": "US", "language": "en",
            "format": "short", "channel_id": channel["id"], "brief": ""
        })
        self.assertTrue(database.channel_delete(channel["id"]))
        self.assertIsNone(database.project_get(project["id"])["channel_id"])


if __name__ == "__main__":
    unittest.main()


class ProductionBatchListTests(unittest.TestCase):
    def test_batch_list_includes_items_and_options(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from app import database
        with tempfile.TemporaryDirectory() as tmp:
            db_path=Path(tmp)/"creatoros-test.db"
            with patch.object(database,"DB_PATH",db_path):
                database.init_db()
                now="2026-01-01T00:00:00+00:00"
                with database._connect() as conn:
                    conn.execute("INSERT INTO strategy_plans(id,name,market,niche,language,channel_id,start_date,days,videos_per_day,plan_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",("strategy-test","Test plan","ID","finance","id",None,"2026-01-01",1,1,"{}",now))
                conn=None
                with database._connect() as conn:
                    conn.execute("INSERT INTO strategy_items(id,plan_id,day_number,planned_date,slot,topic,angle,title,hook,format,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",("strategy-item","strategy-test",1,"2026-01-01",1,"Budget","Simple tips","Budget tips","Start here","short","planned",now))
                batch=database.production_batch_create("strategy-test",[{"id":"strategy-item"}],{"render_video":True})
                rows=database.production_batch_list()
                self.assertEqual(rows[0]["id"],batch["id"])
                self.assertEqual(len(rows[0]["items"]),1)
                self.assertTrue(rows[0]["options"]["render_video"])


class ChannelAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "analytics.db"
        self.path_patcher = patch.object(database, "DB_PATH", self.db_path)
        self.path_patcher.start()
        database.init_db()
        self.channel = database.channel_create({
            "name": "Analytics test", "platform": "youtube",
            "target_market": "ID", "language": "id", "niche": "education"
        })

    def tearDown(self):
        self.path_patcher.stop()
        self.temp_dir.cleanup()

    def test_metric_storage_and_engagement_rate(self):
        database.channel_metric_create({
            "channel_id": self.channel["id"], "publish_job_id": None,
            "metric_date": "2026-10-31", "views": 1000,
            "watch_time_minutes": 250, "likes": 80, "comments": 10,
            "shares": 10, "subscribers_gained": 5, "revenue_amount": 12.5,
            "revenue_currency": "USD", "source": "manual", "notes": ""
        })
        summary = database.channel_analytics_summary(self.channel["id"])
        self.assertEqual(summary["totals"]["views"], 1000)
        self.assertEqual(summary["totals"]["engagement_rate"], 10.0)
        self.assertEqual(summary["totals"]["revenue_amount"], 12.5)
        self.assertEqual(len(database.channel_metric_list(self.channel["id"])), 1)

    def test_mixed_currency_is_not_summed(self):
        common = {
            "publish_job_id": None, "metric_date": "2026-10-31",
            "views": 100, "watch_time_minutes": 10, "likes": 1,
            "comments": 0, "shares": 0, "subscribers_gained": 0,
            "source": "manual", "notes": ""
        }
        database.channel_metric_create({**common, "channel_id": self.channel["id"], "revenue_amount": 10, "revenue_currency": "USD"})
        other = database.channel_create({
            "name": "Second channel", "platform": "youtube",
            "target_market": "GB", "language": "en", "niche": "education"
        })
        database.channel_metric_create({**common, "channel_id": other["id"], "revenue_amount": 8, "revenue_currency": "GBP"})
        summary = database.channel_analytics_summary()
        self.assertEqual(summary["totals"]["revenue_currency"], "mixed")
        self.assertIsNone(summary["totals"]["revenue_amount"])
