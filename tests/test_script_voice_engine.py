import unittest
from unittest.mock import patch
from app.script_voice_engine import available
class ScriptVoiceTests(unittest.TestCase):
 def test_piper_requires_binary_and_model(self):
  with patch("app.script_voice_engine.PIPER_MODEL",""), patch("app.script_voice_engine.shutil.which",return_value="/usr/bin/piper"):
   self.assertFalse(available())
if __name__=="__main__":unittest.main()
