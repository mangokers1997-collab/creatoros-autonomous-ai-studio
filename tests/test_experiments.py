import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class ExperimentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(database, "DB_PATH", Path(self.tmp.name) / "test.db")
        self.patch.start()
        database.init_db()
        plan = database.strategy_plan_create({
            "name": "Test plan", "market": "ID", "niche": "education",
            "language": "id", "channel_id": None, "start_date": "2026-11-01",
            "days": 1, "videos_per_day": 1, "plan_json": json.dumps({})
        }, [{
            "day_number": 1, "planned_date": "2026-11-01", "slot": 1,
            "topic": "Belajar mengatur uang", "angle": "tutorial",
            "title": "Lima cara mengatur uang", "hook": "Gaji cepat habis?",
            "format": "short"
        }])
        self.item_id = plan["items"][0]["id"]

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_create_record_evaluate_and_promote_winner(self):
        exp = database.experiment_create(
            self.item_id, "Hook question improves engagement",
            "Cara mengatur gaji bulanan", "Coba tiga langkah sederhana ini."
        )
        a, b = exp["variants"]
        database.experiment_variant_record(a["id"], {
            "views": 1000, "likes": 100, "comments": 10, "shares": 10,
            "watch_time_minutes": 500, "sample_count": 10
        })
        database.experiment_variant_record(b["id"], {
            "views": 1000, "likes": 30, "comments": 5, "shares": 5,
            "watch_time_minutes": 300, "sample_count": 10
        })
        result = database.experiment_evaluate(exp["id"], minimum_views=100)
        self.assertEqual(result["status"], "winner_found")
        promoted = database.experiment_promote_winner(exp["id"], result["winner"]["id"])
        self.assertEqual(promoted["status"], "promoted")
        updated = database.strategy_plan_get(exp["plan_id"])["items"][0]
        self.assertEqual(updated["title"], a["title"])
        self.assertEqual(updated["status"], "planned")

    def test_no_winner_with_insufficient_views(self):
        exp = database.experiment_create(self.item_id, "Compare hook performance", "Title B", "Hook B")
        result = database.experiment_evaluate(exp["id"], minimum_views=100)
        self.assertEqual(result["status"], "insufficient_data")

    def test_only_one_active_experiment_per_strategy_item(self):
        database.experiment_create(self.item_id, "Compare hook performance", "Title B", "Hook B")
        with self.assertRaises(ValueError):
            database.experiment_create(self.item_id, "Second hypothesis", "Title C", "Hook C")


if __name__ == "__main__":
    unittest.main()
