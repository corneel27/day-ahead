"""Regression for a transient Windows lock during the initial guard read."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("develop", ROOT / "scripts/develop.py")
DEVELOP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVELOP)


class GuardReadTests(unittest.TestCase):
    def test_locked_initial_read_is_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements-lint.txt").write_text("ruff==0.16.10\n")
            original_read = Path.read_text
            attempts = []

            def locked_read(path, *args, **kwargs):
                if path.name == ".ruff.toml" and len(attempts) < 2:
                    attempts.append(path)
                    raise PermissionError("Windows replacement lock")
                return original_read(path, *args, **kwargs)

            with patch.object(DEVELOP, "ROOT", root), patch.object(Path, "read_text", locked_read):
                DEVELOP.write_version_guard()
            self.assertEqual(len(attempts), 2)
            self.assertIn('required-version = "==0.16.10"', (root / ".ruff.toml").read_text())


if __name__ == "__main__":
    unittest.main()
