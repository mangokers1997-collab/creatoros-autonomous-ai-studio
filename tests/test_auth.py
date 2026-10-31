import os
import tempfile
import unittest
from unittest.mock import patch

from app import auth


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CREATOROS_DB_PATH": os.path.join(self.temp.name, "test.db"), "CREATOROS_SESSION_DAYS": "7"})
        self.env.start()
        auth.init_auth_tables()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_owner_setup_login_and_revocation(self):
        user, token = auth.create_owner("creator_owner", "a-very-strong-test-password")
        self.assertEqual(user["username"], "creator_owner")
        self.assertTrue(auth.owner_exists())
        self.assertEqual(auth.get_session(token)["id"], user["id"])
        logged_in, login_token = auth.login("CREATOR_OWNER", "a-very-strong-test-password")
        self.assertEqual(logged_in["id"], user["id"])
        self.assertIsNotNone(auth.get_session(login_token))
        auth.revoke_session(login_token)
        self.assertIsNone(auth.get_session(login_token))
        with self.assertRaises(RuntimeError):
            auth.create_owner("second_owner", "another-strong-password")

    def test_failed_logins_are_throttled(self):
        auth.create_owner("owner_two", "another-very-strong-password")
        for _ in range(5):
            self.assertIsNone(auth.login("owner_two", "incorrect-password"))
        with self.assertRaises(RuntimeError):
            auth.login("owner_two", "another-very-strong-password")

    def test_password_policy(self):
        with self.assertRaises(ValueError):
            auth.create_owner("ab", "short")
        with self.assertRaises(ValueError):
            auth.create_owner("valid_name", "short")

    def test_invalid_session_is_rejected(self):
        self.assertIsNone(auth.get_session(None))
        self.assertIsNone(auth.get_session("not-a-valid-session"))


if __name__ == "__main__":
    unittest.main()
