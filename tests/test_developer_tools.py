"""Exercise real setup, lint and commit hooks in a disposable checkout."""

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path

import yaml

SOURCE = Path(__file__).resolve().parents[1]


class DeveloperToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ruff developer tools ")
        cls.root = Path(cls.temp.name)
        for name in (
            "scripts/develop.py",
            "ruff.toml",
            "requirements-lint.txt",
            "requirements-dev.txt",
            ".pre-commit-config.yaml",
            ".gitignore",
        ):
            target = cls.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        cls.python = (
            cls.root
            / ".venv-tools"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        cls.command("git", "init", "--quiet")
        cls.command("git", "config", "user.name", "Tooling test")
        cls.command("git", "config", "user.email", "tooling@example.invalid")
        cls.command("git", "config", "commit.gpgsign", "false")
        # This existing application environment and hook must survive setup.
        (cls.root / ".venv").mkdir()
        (cls.root / ".venv" / "existing.txt").write_text("keep me")
        hook = cls.root / ".git/hooks/pre-commit"
        hook.write_text(
            "#!/usr/bin/env python\nfrom pathlib import Path\n"
            "Path('hook-ran.txt').write_text('existing-hook')\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        cls.command(sys.executable, "scripts/develop.py", "setup")
        cls.command(sys.executable, "scripts/develop.py", "setup")
        cls.command("git", "add", ".")
        cls.command("git", "commit", "--quiet", "-m", "Fixture")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def command(cls, *args, expected=0):
        environment = dict(os.environ)
        environment["PATH"] = (
            str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
        )
        result = subprocess.run(
            args,
            cwd=cls.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != expected:
            raise AssertionError(
                f"{args}: expected {expected}, got {result.returncode}\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result.stdout + result.stderr

    def test_setup_preserves_environment_and_custom_hook(self):
        self.assertEqual((self.root / ".venv/existing.txt").read_text(), "keep me")
        self.assertTrue((self.root / ".git/hooks/pre-commit.legacy").is_file())
        self.assertEqual(
            (self.root / "hook-ran.txt").read_text().strip(), "existing-hook"
        )
        self.command(str(self.python), "scripts/develop.py", "check")

    def test_tracked_ignored_test_is_fixed_then_blocked_until_corrected(self):
        test = self.root / "dao/tests/probe.py"
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text("import os\n\nprint(missing_name)\n", encoding="utf-8")
        self.command("git", "add", "--force", "dao/tests/probe.py")
        lint = self.command(str(self.python), "scripts/develop.py", "check", expected=1)
        self.assertIn("F401", lint)
        self.assertIn("F821", lint)
        blocked = self.command("git", "commit", "--quiet", "-m", "Invalid", expected=1)
        self.assertIn("F821", blocked)
        self.assertNotIn("import os", test.read_text())
        self.command("git", "add", "--force", "dao/tests/probe.py")
        self.command("git", "commit", "--quiet", "-m", "Still invalid", expected=1)
        test.write_text('print("fixed")\n', encoding="utf-8")
        self.command("git", "add", "--force", "dao/tests/probe.py")
        self.command("git", "commit", "--quiet", "-m", "Valid")
        self.command(str(self.python), "scripts/develop.py", "check")
        self.command(str(self.python), "scripts/develop.py", "hooks")

    def test_custom_hooks_path_is_not_changed(self):
        self.command("git", "config", "core.hooksPath", "custom-hooks")
        try:
            failure = self.command(
                sys.executable, "scripts/develop.py", "setup", expected=1
            )
            self.assertIn("core.hooksPath", failure)
            self.assertEqual(
                self.command("git", "config", "--get", "core.hooksPath").strip(),
                "custom-hooks",
            )
        finally:
            self.command("git", "config", "--unset", "core.hooksPath")

    def test_editor_hook_and_ci_version_agree(self):
        configuration = tomllib.loads((SOURCE / "ruff.toml").read_text())
        pin = configuration["required-version"].removeprefix("==")
        hooks = yaml.safe_load((SOURCE / ".pre-commit-config.yaml").read_text())
        self.assertEqual(hooks["repos"][0]["rev"], f"v{pin}")
        self.assertIn(f"ruff=={pin}", (SOURCE / "requirements-lint.txt").read_text())
        self.assertEqual(
            self.command(str(self.python), "-m", "ruff", "--version").strip(),
            f"ruff {pin}",
        )
        settings = json.loads((SOURCE / ".vscode/settings.json").read_text())
        self.assertEqual(settings["ruff.configurationPreference"], "filesystemFirst")
        executable = settings["ruff.path"][0 if os.name == "nt" else 1]
        executable = executable.replace("${workspaceFolder}", str(self.root))
        self.assertEqual(self.command(executable, "--version").strip(), f"ruff {pin}")

    def test_language_server_matches_cli_and_supplies_save_fix(self):
        executable = self.python.parent / ("ruff.exe" if os.name == "nt" else "ruff")
        process = subprocess.Popen(
            [str(executable), "server"],
            cwd=self.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        messages = queue.Queue()

        def read_messages():
            while True:
                headers = {}
                while (line := process.stdout.readline()) not in (b"\r\n", b""):
                    key, value = line.decode().split(":", 1)
                    headers[key] = value.strip()
                if not headers:
                    return
                messages.put(
                    json.loads(process.stdout.read(int(headers["Content-Length"])))
                )

        reader = threading.Thread(target=read_messages, daemon=True)
        reader.start()

        def send(message):
            payload = json.dumps({"jsonrpc": "2.0", **message}).encode()
            process.stdin.write(
                f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload
            )
            process.stdin.flush()

        def request(identifier, method, params):
            send({"id": identifier, "method": method, "params": params})
            while True:
                response = messages.get(timeout=15)
                if response.get("id") == identifier:
                    self.assertNotIn("error", response)
                    return response["result"]

        text = "import os\n\nprint(missing_name)\n"
        uri = (self.root / "editor_probe.py").as_uri()
        try:
            initialized = request(
                1,
                "initialize",
                {
                    "processId": None,
                    "rootUri": self.root.as_uri(),
                    "capabilities": {"textDocument": {"diagnostic": {}}},
                    "workspaceFolders": [{"uri": self.root.as_uri(), "name": "test"}],
                },
            )
            pin = tomllib.loads((SOURCE / "ruff.toml").read_text())["required-version"][
                2:
            ]
            self.assertEqual(initialized["serverInfo"]["version"], pin)
            send({"method": "initialized", "params": {}})
            send(
                {
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "python",
                            "version": 1,
                            "text": text,
                        }
                    },
                }
            )
            diagnostics = request(
                2, "textDocument/diagnostic", {"textDocument": {"uri": uri}}
            )
            cli = subprocess.run(
                [
                    str(executable),
                    "check",
                    "--stdin-filename",
                    "editor_probe.py",
                    "--output-format",
                    "json",
                    "-",
                ],
                cwd=self.root,
                input=text,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cli.returncode, 1)
            self.assertEqual(
                {item["code"] for item in diagnostics["items"]},
                {item["code"] for item in json.loads(cli.stdout)},
            )
            actions = request(
                3,
                "textDocument/codeAction",
                {
                    "textDocument": {"uri": uri},
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 3, "character": 0},
                    },
                    "context": {"diagnostics": [], "only": ["source.fixAll.ruff"]},
                },
            )
            edits = actions[0]["edit"]["changes"][uri]
            self.assertEqual(
                edits,
                [
                    {
                        "newText": "",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 1, "character": 0},
                        },
                    }
                ],
            )
            send(
                {
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": uri, "version": 2},
                        "contentChanges": [{"text": "\nprint(missing_name)\n"}],
                    },
                }
            )
            remaining = request(
                4, "textDocument/diagnostic", {"textDocument": {"uri": uri}}
            )
            self.assertEqual([item["code"] for item in remaining["items"]], ["F821"])
        finally:
            process.kill()
            process.wait(timeout=10)
            reader.join(timeout=10)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
