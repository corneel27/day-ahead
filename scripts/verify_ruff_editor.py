"""Prepare and open an isolated native VS Code Ruff acceptance workspace."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / ".local/ruff-editor-workspace"
PROFILE = ROOT / ".local/ruff-editor-native-user-data"
MARKER = WORKSPACE / ".ruff-editor-owned"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "open", "run"))
    action = parser.parse_args().action
    code = shutil.which("code")
    if code is None:
        raise SystemExit("Install VS Code on this host and make its code command available.")
    if action == "prepare":
        if WORKSPACE.exists() and not MARKER.is_file():
            raise SystemExit("Existing editor workspace is not owned by this verifier; leave it intact.")
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        MARKER.write_text("Generated isolated Ruff acceptance workspace.\n", encoding="utf-8")
        for name in (
            "ruff.toml", "requirements-lint.txt", "requirements-dev.txt",
            ".pre-commit-config.yaml", "scripts/develop.py",
            "tools/ruff_guard/pyproject.toml", "tools/ruff_guard/ruff_guard.py",
            "tests/ruff_adoption_cases.json", ".vscode/settings.json",
        ):
            target = WORKSPACE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        settings_path = WORKSPACE / ".vscode/settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        python = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        # This fixture tests Ruff only; it intentionally has no application venv.
        settings["python.defaultInterpreterPath"] = f"${{workspaceFolder}}/.venv-tools/{python}"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=WORKSPACE, check=True)
        try:
            subprocess.run([sys.executable, "scripts/develop.py", "setup"], cwd=WORKSPACE, check=True)
        except subprocess.CalledProcessError:
            raise SystemExit("Editor-tool setup failed. Close any earlier verification window before preparing again; inspect the setup output above.") from None
        print("Editor workspace prepared. Run this script with 'open', then trust that local workspace.")
        return
    if not MARKER.is_file():
        raise SystemExit("Run this script with 'prepare' first.")
    arguments = [code, "--new-window", "--user-data-dir", str(PROFILE)]
    if action == "run":
        located = subprocess.run([code, "--locate-extension", "charliermarsh.ruff"], capture_output=True, text=True, check=True)
        extension = Path(located.stdout.strip())
        if not (extension / "package.json").is_file():
            raise SystemExit("Install the Ruff extension in host VS Code before running this test.")
        request = WORKSPACE / ".local/run-ruff-acceptance"
        request.parent.mkdir(exist_ok=True)
        request.write_text("Run the requested editor acceptance suite.\n", encoding="utf-8")
        arguments += [
            "--extensionDevelopmentPath", str(ROOT / "tests/vscode_ruff_adoption"),
            "--extensionDevelopmentPath", str(extension),
        ]
    subprocess.run([*arguments, str(WORKSPACE)], cwd=ROOT, check=True)
    print("Use the trusted local test window; do not reopen it in a Dev Container.")
    print(f"Results: {WORKSPACE / '.local/ruff-editor-acceptance/results.json'}")


if __name__ == "__main__":
    main()
