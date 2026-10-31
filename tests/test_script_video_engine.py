import unittest
from unittest.mock import patch
from app import script_video_engine as engine
class ScriptVideoEngineTests(unittest.TestCase):
 def test_job_requires_matching_script_and_voice_job(self):
  with patch.object(engine,"get_script",return_value={"id":"script"}),patch.object(engine,"get_voice_job",return_value={"id":"voice","script_id":"different"}):
   self.assertIsNone(engine.create_job("script","voice"))
if __name__=="__main__":unittest.main()
