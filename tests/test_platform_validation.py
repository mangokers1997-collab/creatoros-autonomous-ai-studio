import unittest
from app.platform_validation import validate_publish_metadata

class PlatformMetadataValidationTests(unittest.TestCase):
    def test_platform_character_limits_are_reported(self):
        result=validate_publish_metadata("youtube","A title","A caption")
        self.assertTrue(result["valid"])
        self.assertEqual(result["limits"]["title_max"],100)

    def test_overlong_title_is_rejected(self):
        result=validate_publish_metadata("youtube","x"*101,"")
        self.assertFalse(result["valid"])
        self.assertTrue(any("100 characters" in error for error in result["errors"]))

    def test_caption_limit_is_platform_specific(self):
        result=validate_publish_metadata("instagram","Title","x"*2201)
        self.assertFalse(result["valid"])

if __name__ == "__main__":
    unittest.main()
