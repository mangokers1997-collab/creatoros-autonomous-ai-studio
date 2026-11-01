import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class ProductionWorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "worker.db"
        self.patch = patch.object(database, "DB_PATH", self.db_path)
        self.patch.start()
        database.init_db()
        now = "2026-11-01T00:00:00+00:00"
        with database._connect() as conn:
            conn.execute(
                """INSERT INTO strategy_plans
                (id,name,market,niche,language,channel_id,start_date,days,videos_per_day,plan_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                ("plan-1","Plan","ID","education","id",None,"2026-11-01",1,1,"{}",now),
            )
        self.orchestration = database.production_orchestration_create(
            [{"strategy_id":"plan-1","channel_id":None}], {"max_items":1}
        )

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_claim_is_exclusive_until_lease_expires(self):
        claimed = database.production_orchestration_claim_next(
            "worker-a","2026-11-01T00:02:00+00:00","2026-11-01T00:00:00+00:00"
        )
        self.assertEqual(claimed["id"], self.orchestration["id"])
        self.assertIsNone(database.production_orchestration_claim_next(
            "worker-b","2026-11-01T00:03:00+00:00","2026-11-01T00:00:30+00:00"
        ))

    def test_expired_lease_requeues_for_recovery(self):
        first = database.production_orchestration_claim_next(
            "worker-a","2026-11-01T00:01:00+00:00","2026-11-01T00:00:00+00:00"
        )
        item_id = first["items"][0]["id"]
        database.production_orchestration_item_update(item_id,"processing")
        recovered = database.production_orchestration_claim_next(
            "worker-b","2026-11-01T00:04:00+00:00","2026-11-01T00:02:00+00:00"
        )
        self.assertEqual(recovered["id"], self.orchestration["id"])
        self.assertEqual(recovered["attempts"], 2)
        self.assertEqual(recovered["items"][0]["status"], "queued")
        self.assertEqual(recovered["worker_id"], "worker-b")

    def test_worker_heartbeat_requires_lease_owner(self):
        database.production_orchestration_claim_next(
            "worker-a","2026-11-01T00:02:00+00:00","2026-11-01T00:00:00+00:00"
        )
        self.assertFalse(database.production_orchestration_heartbeat(
            self.orchestration["id"],"worker-b","2026-11-01T00:03:00+00:00"
        ))
        self.assertTrue(database.production_orchestration_heartbeat(
            self.orchestration["id"],"worker-a","2026-11-01T00:03:00+00:00"
        ))


if __name__ == "__main__":
    unittest.main()
