import unittest
from unittest.mock import patch

from app.production_orchestrator import create_production_orchestration


class ProductionOrchestratorTests(unittest.TestCase):
    @patch("app.production_orchestrator.database.strategy_plan_get")
    @patch("app.production_orchestrator.database.production_orchestration_create")
    def test_validates_and_persists_selected_channel_plans(self, create, get_plan):
        get_plan.side_effect = [
            {"id":"p1","name":"Finance","channel_id":"c1","items":[{"status":"planned"}]},
            {"id":"p2","name":"Cooking","channel_id":"c2","items":[{"status":"planned"}]},
        ]
        create.return_value = {"id":"o1","items":[]}
        result = create_production_orchestration(["p1","p2"], 3, False, False, 48)
        self.assertEqual(result["id"], "o1")
        records = create.call_args.args[0]
        self.assertEqual(records, [
            {"strategy_id":"p1","channel_id":"c1"},
            {"strategy_id":"p2","channel_id":"c2"},
        ])
        self.assertEqual(create.call_args.args[1]["execution_mode"], "sequential_single_worker")

    @patch("app.production_orchestrator.database.strategy_plan_get", return_value={
        "id":"p1","name":"Finance","channel_id":"c1","items":[{"status":"planned"}]
    })
    def test_rejects_two_plans_for_same_channel(self, _get):
        with self.assertRaises(ValueError):
            create_production_orchestration(["p1","p1b"], 2, False, False, 48)

    @patch("app.production_orchestrator.database.strategy_plan_get", return_value={
        "id":"p1","name":"General","channel_id":None,"items":[{"status":"planned"}]
    })
    def test_rejects_unassigned_strategy(self, _get):
        with self.assertRaises(ValueError):
            create_production_orchestration(["p1"], 2, False, False, 48)

    def test_rejects_capacity_overflow(self):
        with self.assertRaises(ValueError):
            create_production_orchestration(["p1"], 6, False, False, 48)


if __name__ == "__main__":
    unittest.main()
