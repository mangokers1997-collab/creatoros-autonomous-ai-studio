
import unittest
from unittest.mock import patch
from app import script_video_engine as engine

class ScriptVideoEngineTests(unittest.TestCase):
    def test_job_requires_matching_script_and_voice_job(self):
        with patch.object(engine, "get_script", return_value={"id": "script", "content": {"scenes": []}}), patch.object(engine, "get_voice_job", return_value={"id": "voice", "script_id": "different"}):
            self.assertIsNone(engine.create_job("script", "voice"))

    def test_rejects_more_than_twelve_scene_images(self):
        with patch.object(engine, "get_script", return_value={"id": "script", "content": {"scenes": []}}), patch.object(engine, "get_voice_job", return_value={"id": "voice", "script_id": "script"}):
            self.assertIsNone(engine.create_job("script", "voice", ["x"] * 13))

    def test_rejects_scene_image_count_mismatch(self):
        with patch.object(engine, "get_script", return_value={"id": "script", "content": {"scenes": [{"scene": 1}, {"scene": 2}]}}), patch.object(engine, "get_voice_job", return_value={"id": "voice", "script_id": "script"}):
            self.assertIsNone(engine.create_job("script", "voice", ["asset-one"]))

    def test_rejects_non_image_assets(self):
        with patch.object(engine, "get_script", return_value={"id": "script", "content": {"scenes": [{"scene": 1}]}}), patch.object(engine, "get_voice_job", return_value={"id": "voice", "script_id": "script"}), patch.object(engine, "media_asset_get", return_value={"id": "asset", "media_type": "audio"}):
            self.assertIsNone(engine.create_job("script", "voice", ["asset"]))

if __name__ == "__main__":
    unittest.main()


class VideoQualityEngineTests(unittest.TestCase):
    def test_unknown_job_returns_none(self):
        from app.video_quality_engine import inspect_video
        with patch("app.video_quality_engine.get_job",return_value=None):
            self.assertIsNone(inspect_video("missing"))

    def test_non_ready_job_returns_not_ready_report(self):
        from app.video_quality_engine import inspect_video
        with patch("app.video_quality_engine.get_job",return_value={"id":"j","status":"rendering"}):
            result=inspect_video("j")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"],"not_ready")
