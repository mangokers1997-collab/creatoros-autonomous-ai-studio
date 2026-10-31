import unittest
from app.script_engine import generate_script
class ScriptEngineTests(unittest.TestCase):
 def test_structured_script(self):
  x=generate_script({"topic":"mengatur uang","language":"id","duration_seconds":60})
  self.assertGreaterEqual(len(x["content"]["scenes"]),3)
  self.assertTrue(x["content"]["fact_check_checklist"])
  self.assertEqual(x["engine"],"template_fallback")
 def test_supported_locales(self):
  for lang in ("en","ja","ar"): self.assertTrue(generate_script({"topic":"daily habits","language":lang})["content"]["hook"])
 def test_validation(self):
  with self.assertRaises(ValueError): generate_script({"topic":"ok topic","duration_seconds":10})
  with self.assertRaises(ValueError): generate_script({"topic":"ok topic","language":"xx"})
if __name__=="__main__": unittest.main()
