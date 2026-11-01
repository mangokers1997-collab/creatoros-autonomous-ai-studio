import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.resource_scheduler import resource_snapshot


class ResourceSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "CREATOROS_MEDIA_DIR": self.tmp.name,
            "CREATOROS_RESOURCE_GUARD_ENABLED": "true",
            "CREATOROS_RESOURCE_MODE": "conservative",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    @patch("app.resource_scheduler._memory_available_mb", return_value=1024.0)
    @patch("app.resource_scheduler._cpu_load_per_core", return_value=0.2)
    @patch("app.resource_scheduler.shutil.disk_usage",
           return_value=SimpleNamespace(free=20 * 1024**3, total=100 * 1024**3))
    def test_low_memory_blocks_new_job_admission(self, *_mocks):
        result = resource_snapshot()
        self.assertFalse(result["can_start_job"])
        self.assertEqual(result["status"], "blocked")
        self.assertIn("memory", result["blocked_reasons"])

    @patch("app.resource_scheduler._memory_available_mb", return_value=8192.0)
    @patch("app.resource_scheduler._cpu_load_per_core", return_value=0.1)
    @patch("app.resource_scheduler.shutil.disk_usage",
           return_value=SimpleNamespace(free=20 * 1024**3, total=100 * 1024**3))
    def test_sufficient_headroom_allows_job(self, *_mocks):
        result = resource_snapshot()
        self.assertTrue(result["can_start_job"])
        self.assertEqual(result["status"], "ready")

    @patch("app.resource_scheduler._memory_available_mb", return_value=None)
    @patch("app.resource_scheduler._cpu_load_per_core", return_value=None)
    @patch("app.resource_scheduler.shutil.disk_usage",
           return_value=SimpleNamespace(free=20 * 1024**3, total=100 * 1024**3))
    def test_unknown_host_metrics_are_reported_without_deadlock(self, *_mocks):
        result = resource_snapshot()
        self.assertTrue(result["can_start_job"])
        self.assertEqual(result["status"], "monitoring_limited")
        self.assertIn("memory", result["unknown_metrics"])

    @patch.dict(os.environ, {"CREATOROS_RESOURCE_GUARD_ENABLED": "false"})
    @patch("app.resource_scheduler._memory_available_mb", return_value=100.0)
    @patch("app.resource_scheduler._cpu_load_per_core", return_value=9.0)
    @patch("app.resource_scheduler.shutil.disk_usage",
           return_value=SimpleNamespace(free=100, total=1000))
    def test_guard_can_be_disabled_explicitly(self, *_mocks):
        result = resource_snapshot()
        self.assertTrue(result["can_start_job"])
        self.assertEqual(result["blocked_reasons"], [])


if __name__ == "__main__":
    unittest.main()
