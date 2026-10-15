"""Regressions for transient file errors during guard checks and upgrades."""

import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("develop", ROOT / "scripts/develop.py")
DEVELOP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVELOP)


class GuardReadTests(unittest.TestCase):
    def test_watcher_recovers_after_transient_file_errors(self):
        for fault in ("pin", "ruff", "launcher", "version-check"):
            with self.subTest(fault=fault):
                self.assert_watcher_recovers(fault)

    def assert_watcher_recovers(self, fault):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pin = root / "requirements-lint.txt"
            pin.write_text("ruff==0.16.10\n")
            tools = root / ".venv-tools"
            tools.mkdir()
            ruff = tools / "ruff"
            ruff.touch()
            launcher = tools / ("ruff-project.exe" if os.name == "nt" else "ruff-project")
            launcher.touch()
            output = io.StringIO()
            original_read = Path.read_bytes
            original_stat = Path.stat
            original_exists = Path.exists
            stat_calls = 0
            read_calls = 0

            def read(path):
                nonlocal read_calls
                if path == pin:
                    read_calls += 1
                    if fault == "pin" and read_calls == 1:
                        raise FileNotFoundError("pin replaced during checkout")
                return original_read(path)

            def exists(path):
                if path in (ruff, launcher):
                    return True
                return original_exists(path)

            def stat(path, *args, **kwargs):
                nonlocal stat_calls
                target = ruff if fault == "ruff" else launcher
                if fault in ("ruff", "launcher") and path == target:
                    stat_calls += 1
                    # Fail the explicit timestamp read after exists() succeeds,
                    # independently of how pathlib implements exists().
                    if stat_calls == 1:
                        raise FileNotFoundError("executable replaced during upgrade")
                return original_stat(path, *args, **kwargs)

            version_results = (
                [PermissionError("temporary guard lock"), "0.16.10"]
                if fault == "version-check" else ["0.16.10"]
            )
            with patch.object(DEVELOP, "ROOT", root), \
                    patch.object(DEVELOP, "TOOLS", tools), \
                    patch.object(DEVELOP, "RUFF", ruff), \
                    patch.object(Path, "read_bytes", read), \
                    patch.object(Path, "exists", exists), \
                    patch.object(Path, "stat", stat), \
                    patch.object(DEVELOP, "check_version", side_effect=version_results) as check, \
                    patch.object(DEVELOP.time, "sleep", side_effect=[None, None, KeyboardInterrupt]), \
                    patch("sys.stdout", output), \
                    self.assertRaises(KeyboardInterrupt):
                DEVELOP.watch_versions()
            messages = output.getvalue()
            self.assertEqual(messages.count("error:"), 1)
            self.assertEqual(messages.count("is ready"), 1)
            self.assertLess(messages.index("error:"), messages.index("is ready"))
            self.assertEqual(check.call_count, len(version_results))

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
