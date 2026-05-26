import os
import unittest

from utils.security import validate_password_strength
from utils.file_security import build_safe_file_path


class SecurityBasicsTestCase(unittest.TestCase):
    def test_password_strength_accepts_valid_password(self):
        ok, _ = validate_password_strength("TempPass123")
        self.assertTrue(ok)

    def test_password_strength_rejects_short_password(self):
        ok, _ = validate_password_strength("Abc123")
        self.assertFalse(ok)

    def test_backup_path_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            build_safe_file_path("backups", "../secrets.json", suffix=".json")

    def test_backup_path_accepts_json_filename(self):
        path = build_safe_file_path("backups", "manual_20260526.json", suffix=".json")
        expected_root = os.path.abspath("backups")
        self.assertTrue(os.path.abspath(path).startswith(expected_root))


if __name__ == "__main__":
    unittest.main()
