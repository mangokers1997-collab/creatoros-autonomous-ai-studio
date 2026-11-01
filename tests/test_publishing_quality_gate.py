import json
import tempfile
import unittest
from unittest.mock import patch, Mock

from app.publishing_quality_gate import inspect_publish_readiness


class PublishingQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.tmp.write(b"x" * 4096)
        self.tmp.close()
        self.channel = {"id": "c1", "platform": "youtube"}
        self.project = {"id": "p1", "channel_id": "c1", "status": "approved"}
        self.render = {"id": "r1", "project_id": "p1", "status": "rendered",
                       "output_path": self.tmp.name}

    def tearDown(self):
        import os
        os.unlink(self.tmp.name)

    @patch("app.publishing_quality_gate.publish_job_list", return_value=[])
    @patch("app.publishing_quality_gate.subprocess.run")
    @patch("app.publishing_quality_gate.shutil.which", return_value="/usr/bin/ffprobe")
    @patch("app.publishing_quality_gate.render_job_get")
    @patch("app.publishing_quality_gate.project_get")
    @patch("app.publishing_quality_gate.channel_get")
    def test_ready_video_passes_technical_gate(self, channel, project, render, _which, probe, _jobs):
        channel.return_value = self.channel
        project.return_value = self.project
        render.return_value = self.render
        probe.return_value = Mock(returncode=0, stdout=json.dumps({
            "format": {"duration": "30", "format_name": "mov,mp4"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }), stderr="")
        result = inspect_publish_readiness("c1", "p1", "r1", "Valid title", "Caption")
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "ready_for_human_review")
        self.assertTrue(result["human_review_required"])

    @patch("app.publishing_quality_gate.channel_get", return_value=None)
    @patch("app.publishing_quality_gate.project_get", return_value=None)
    @patch("app.publishing_quality_gate.render_job_get", return_value=None)
    def test_missing_assets_block_readiness(self, *_mocks):
        result = inspect_publish_readiness("missing", "missing", "missing", "", "")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "blocked")

    @patch("app.publishing_quality_gate.publish_job_list", return_value=[
        {"title": "Same title", "project_id": "another-project"}
    ])
    @patch("app.publishing_quality_gate.subprocess.run")
    @patch("app.publishing_quality_gate.shutil.which", return_value="/usr/bin/ffprobe")
    @patch("app.publishing_quality_gate.render_job_get")
    @patch("app.publishing_quality_gate.project_get")
    @patch("app.publishing_quality_gate.channel_get")
    def test_duplicate_title_is_warning_not_blocker(self, channel, project, render, _which, probe, _jobs):
        channel.return_value = self.channel
        project.return_value = self.project
        render.return_value = self.render
        probe.return_value = Mock(returncode=0, stdout=json.dumps({
            "format": {"duration": "30"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }), stderr="")
        result = inspect_publish_readiness("c1", "p1", "r1", "Same title", "Caption")
        self.assertTrue(result["passed"])
        self.assertIn("Duplicate title check", result["warnings"])


if __name__ == "__main__":
    unittest.main()
