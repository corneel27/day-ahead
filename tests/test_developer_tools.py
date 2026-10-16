"""Exercise real setup, lint and commit hooks in a disposable checkout."""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

SOURCE = Path(__file__).resolve().parents[1]
ADOPTION_CASES = json.loads((SOURCE / "tests/ruff_adoption_cases.json").read_text())


def pinned_version():
    return next(
        line.split("==", 1)[1]
        for line in (SOURCE / "requirements-lint.txt").read_text().splitlines()
        if line.startswith("ruff==")
    )


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
            "tools/ruff_guard/pyproject.toml",
            "tools/ruff_guard/ruff_guard.py",
        ):
            target = cls.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        # Exercise future adoption rules only in the disposable test checkout.
        # The production rule selection is not changed by a Ruff version bump.
        fixture_config = cls.root / "ruff.toml"
        configuration = fixture_config.read_text()
        if "extend-select" not in configuration:
            codes = json.dumps([case["code"] for case in ADOPTION_CASES])
            fixture_config.write_text(configuration.replace("[lint]\n", f"[lint]\nextend-select = {codes}\n"))
        cls.fixture_config = fixture_config.read_bytes()
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

    def test_concurrent_version_checks_generate_a_complete_guard(self):
        generated = self.root / ".ruff.toml"
        generated.unlink()
        with ThreadPoolExecutor(max_workers=6) as executor:
            outputs = list(
                executor.map(
                    lambda _: self.command(
                        str(self.python), "scripts/develop.py", "status"
                    ),
                    range(6),
                )
            )
        self.assertTrue(
            all("matches requirements-lint.txt" in output for output in outputs)
        )
        self.assertEqual(
            tomllib.loads(generated.read_text())["required-version"],
            f"=={pinned_version()}",
        )

    def test_existing_personal_ruff_configuration_is_preserved(self):
        generated = self.root / ".ruff.toml"
        original = generated.read_text()
        personal = "line-length = 100\n"
        try:
            generated.write_text(personal)
            message = self.command(
                str(self.python), "scripts/develop.py", "status", expected=1
            )
            self.assertIn("configuration conflict", message)
            self.assertEqual(generated.read_text(), personal)
        finally:
            generated.write_text(original)

    def test_editor_hook_and_ci_version_agree(self):
        configuration = tomllib.loads((SOURCE / "ruff.toml").read_text())
        self.assertNotIn("required-version", configuration)
        expected_rules = {case["code"] for case in ADOPTION_CASES}
        self.assertEqual(expected_rules, set(configuration["lint"]["extend-select"]))
        fixture = tomllib.loads(self.fixture_config.decode())
        self.assertEqual(expected_rules, set(fixture["lint"]["extend-select"]))
        pin = pinned_version()
        hooks = yaml.safe_load((SOURCE / ".pre-commit-config.yaml").read_text())
        self.assertEqual(hooks["repos"][0]["repo"], "local")
        self.assertNotIn("rev", hooks["repos"][0])
        self.assertIn(f"ruff=={pin}", (SOURCE / "requirements-lint.txt").read_text())
        self.assertEqual(
            self.command(str(self.python), "-m", "ruff", "--version").strip(),
            f"ruff {pin}",
        )
        settings = json.loads((SOURCE / ".vscode/settings.json").read_text())
        self.assertEqual(settings["ruff.configurationPreference"], "filesystemFirst")
        for override in ("ruff.configuration", "ruff.lint.select", "ruff.lint.extendSelect", "ruff.lint.ignore", "ruff.exclude", "ruff.lineLength"):
            self.assertNotIn(override, settings)
        executable = settings["ruff.path"][0 if os.name == "nt" else 1]
        executable = executable.replace("${workspaceFolder}", str(self.root))
        self.assertEqual(self.command(executable, "--version").strip(), f"ruff {pin}")

    def test_adopted_rules_use_the_same_effective_settings_and_hook(self):
        probe = self.root / "adoption_probe.py"
        try:
            probe.write_text('print("ready")\n', encoding="utf-8")
            editor = self.command(str(self.python), "-m", "ruff", "check", "--show-settings", str(probe))
            ci = self.command(str(self.python), "-m", "ruff", "check", "--config", "ruff.toml", "--show-settings", str(probe))
            self.assertEqual(editor.partition("# General Settings")[2], ci.partition("# General Settings")[2])
            for case in ADOPTION_CASES:
                with self.subTest(rule=case["code"]):
                    probe.write_text(case["invalid"], encoding="utf-8")
                    self.command("git", "add", probe.name)
                    cli = self.command(str(self.python), "-m", "ruff", "check", probe.name, "--output-format", "json", expected=1)
                    self.assertIn(case["code"], {item["code"] for item in json.loads(cli)})
                    ci_failure = self.command(str(self.python), "scripts/develop.py", "ci-check", expected=1)
                    self.assertIn(case["code"], ci_failure)
                    original = probe.read_text()
                    hook = self.command(str(self.python), "-m", "pre_commit", "run", "ruff-check", "--files", probe.name, expected=1)
                    self.assertTrue(case["code"] in hook or probe.read_text() != original)
                    probe.write_text(case["corrected"], encoding="utf-8")
                    self.command("git", "add", probe.name)
                    self.command(str(self.python), "-m", "pre_commit", "run", "ruff-check", "--files", probe.name)
                    self.command(str(self.python), "scripts/develop.py", "ci-check")
        finally:
            self.command("git", "rm", "--cached", "--ignore-unmatch", probe.name)
            probe.unlink(missing_ok=True)

    def test_language_server_matches_cli_and_supplies_save_fix(self):
        executable = (
            self.root
            / ".venv-tools"
            / ("ruff-project.exe" if os.name == "nt" else "ruff-project")
        )
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
            pin = pinned_version()
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
            # Exercise every newly adopted rule through the real server with
            # the same fixtures used by CI and the configured commit hook.
            for index, case in enumerate(ADOPTION_CASES):
                with self.subTest(rule=case["code"]):
                    for repaired, content in enumerate((case["invalid"], case["corrected"])):
                        send({"method": "textDocument/didChange", "params": {
                            "textDocument": {"uri": uri, "version": 3 + index * 2 + repaired},
                            "contentChanges": [{"text": content}],
                        }})
                        response = request(100 + index * 2 + repaired, "textDocument/diagnostic", {"textDocument": {"uri": uri}})
                        result = subprocess.run([str(executable), "check", "--stdin-filename", "editor_probe.py", "--output-format", "json", "-"], cwd=self.root, input=content, capture_output=True, text=True, check=False)
                        self.assertIn(result.returncode, (0, 1), result.stderr)
                        codes = {item["code"] for item in json.loads(result.stdout)}
                        self.assertEqual({item["code"] for item in response["items"]}, codes)
                        if repaired:
                            self.assertEqual(codes, set())
                        else:
                            self.assertIn(case["code"], codes)
            # A checkout upgrade during the editor session stops the old server.
            requirements = self.root / "requirements-lint.txt"
            original = requirements.read_text()
            try:
                requirements.write_text(original.replace(f"ruff=={pin}", "ruff==0.0.0"))
                self.assertNotEqual(process.wait(timeout=10), 0)
                self.assertIn("Restart Server", process.stderr.read().decode())
            finally:
                requirements.write_text(original)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            reader.join(timeout=10)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()

    def test_version_change_blocks_cli_editor_and_non_python_commit(self):
        requirements = self.root / "requirements-lint.txt"
        original = requirements.read_text()
        pin = pinned_version()
        executable = (
            self.root
            / ".venv-tools"
            / ("ruff-project.exe" if os.name == "nt" else "ruff-project")
        )
        try:
            requirements.write_text(original.replace(f"ruff=={pin}", "ruff==0.0.0"))
            for action in ("status", "check", "fix", "hooks", "ci-check"):
                message = self.command(
                    str(self.python), "scripts/develop.py", action, expected=1
                )
                self.assertIn("requires Ruff 0.0.0", message)
                self.assertIn("Set up Ruff", message)
            self.command(str(executable), "server", expected=1)
            self.command("git", "add", "requirements-lint.txt")
            blocked = self.command(
                "git", "commit", "--quiet", "-m", "Stale tooling", expected=1
            )
            self.assertIn("requires Ruff 0.0.0", blocked)
            generated = tomllib.loads((self.root / ".ruff.toml").read_text())
            self.assertEqual(generated["required-version"], "==0.0.0")
            # Even an unguarded or bundled Ruff is prevented from using stale rules.
            self.command(str(self.python), "-m", "ruff", "check", ".", expected=2)
        finally:
            requirements.write_text(original)
            self.command("git", "add", "requirements-lint.txt")
            self.command(str(self.python), "scripts/develop.py", "status")

    def test_missing_guard_in_an_existing_environment_has_repair_message(self):
        launcher = (
            self.root
            / ".venv-tools"
            / ("ruff-project.exe" if os.name == "nt" else "ruff-project")
        )
        backup = launcher.with_name(launcher.name + ".backup")
        launcher.rename(backup)
        try:
            message = self.command(
                str(self.python), "scripts/develop.py", "status", expected=1
            )
            self.assertIn("version guard is missing", message)
            self.assertIn("Set up Ruff", message)
        finally:
            backup.rename(launcher)

    def test_upgrade_changes_only_requirements_pin_and_setup_repairs(self):
        requirements = self.root / "requirements-lint.txt"
        original = requirements.read_text()
        # Exercise a real published release, not a mocked pip or Ruff binary.
        alternate = "0.17.0" if pinned_version() != "0.17.0" else "0.16.10"
        try:
            requirements.write_text(
                original.replace(f"ruff=={pinned_version()}", f"ruff=={alternate}")
            )
            self.command(str(self.python), "scripts/develop.py", "status", expected=1)
            self.command(str(self.python), "scripts/develop.py", "setup")
            self.assertIn(
                f"Ruff {alternate} matches",
                self.command(str(self.python), "scripts/develop.py", "status"),
            )
            self.command(str(self.python), "scripts/develop.py", "hooks")
            self.command(str(self.python), "scripts/develop.py", "ci-check")
            self.assertEqual(
                (self.root / "ruff.toml").read_bytes(),
                self.fixture_config,
            )
            self.assertEqual(
                (self.root / ".pre-commit-config.yaml").read_bytes(),
                (SOURCE / ".pre-commit-config.yaml").read_bytes(),
            )
        finally:
            requirements.write_text(original)
            self.command(str(self.python), "scripts/develop.py", "setup")

    def test_workspace_watch_reports_upgrade_without_installing(self):
        tasks = json.loads((SOURCE / ".vscode/tasks.json").read_text())
        task = next(item for item in tasks["tasks"] if item["label"] == "Development: Watch Ruff version")
        runner = task.get("windows", task) if os.name == "nt" else task
        # Exercise the configured folder-open command without activating any
        # VS Code extension; a command-variable dependency would fail here.
        process = subprocess.Popen(
            [runner["command"], *runner["args"]],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines = queue.Queue()
        reader = threading.Thread(
            target=lambda: [lines.put(line) for line in process.stdout], daemon=True
        )
        reader.start()
        requirements = self.root / "requirements-lint.txt"
        original = requirements.read_text()

        def status_line():
            while (line := lines.get(timeout=15)).startswith(
                "Ruff version check started"
            ):
                pass
            return line

        try:
            self.assertIn("is ready", status_line())
            requirements.write_text(
                original.replace(f"ruff=={pinned_version()}", "ruff==0.0.0")
            )
            warning = status_line()
            self.assertIn("requires Ruff 0.0.0", warning)
            matcher = tasks["tasks"][0]["problemMatcher"][0]
            match = re.match(matcher["pattern"]["regexp"], warning)
            self.assertIsNotNone(match)
            self.assertEqual(
                match.group(matcher["pattern"]["file"]), "requirements-lint.txt"
            )
            requirements.write_text(original)
            self.assertIn("is ready", status_line())
            # Repairing the launcher does not reinstall an unchanged Ruff binary.
            launcher = self.root / ".venv-tools" / (
                "ruff-project.exe" if os.name == "nt" else "ruff-project"
            )
            backup = launcher.with_name(launcher.name + ".watch-backup")
            launcher.rename(backup)
            try:
                self.assertIn("version guard is missing", status_line())
            finally:
                backup.rename(launcher)
            self.assertIn("is ready", status_line())
            self.assertEqual(
                self.command(str(self.python), "-m", "ruff", "--version").strip(),
                f"ruff {pinned_version()}",
            )
        finally:
            requirements.write_text(original)
            process.terminate()
            process.wait(timeout=10)
            reader.join(timeout=10)
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
