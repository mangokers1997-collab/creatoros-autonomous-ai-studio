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
                    conn.execute("INSERT INTO strategy_plans(id,niche,market,language,start_date,days,videos_per_day,created_at) VALUES(?,?,?,?,?,?,?,?)",("strategy-test","finance","ID","id","2026-01-01",1,1,now))
                batch=database.production_batch_create("strategy-test",[{"id":"strategy-item"}],{"render_video":True})
                rows=database.production_batch_list()
                self.assertEqual(rows[0]["id"],batch["id"])
                self.assertEqual(len(rows[0]["items"]),1)
                self.assertTrue(rows[0]["options"]["render_video"])
