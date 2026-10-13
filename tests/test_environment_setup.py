"""Verify preview isolation and preservation without installing dependencies."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("setup_environment", ROOT / "scripts/setup_environment.py")
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class PreviewSetupTests(unittest.TestCase):
    def test_repeat_setup_preserves_preview_and_application_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application = root / "dao/data"
            application.mkdir(parents=True)
            (application / "options_example.json").write_text('{"homeassistant": {}}')
            original = application / "options.json"
            original.write_text('{"private": "unchanged"}')
            preview = root / ".local/web-data"
            with patch.object(SETUP, "ROOT", root), patch.object(SETUP, "DATA", preview):
                SETUP.prepare_preview()
                self.assertEqual(json.loads((preview / "options.json").read_text())["homeassistant"]["host"], "127.0.0.1")
                self.assertEqual((preview / "secrets.json").read_text(), "{}\n")
                (preview / "options.json").write_text('{"edited": true}')
                (preview / "secrets.json").write_text('{"edited": true}')
                SETUP.prepare_preview()
                self.assertEqual((preview / "options.json").read_text(), '{"edited": true}')
                self.assertEqual((preview / "secrets.json").read_text(), '{"edited": true}')
                self.assertEqual(original.read_text(), '{"private": "unchanged"}')
                self.assertTrue((preview / "images").is_dir())
                self.assertTrue((preview / "log").is_dir())


if __name__ == "__main__":
    unittest.main()
