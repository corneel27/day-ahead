"""Set up and run isolated developer tools on Windows, Linux and macOS."""

import argparse
import os
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".venv-tools"
PYTHON = TOOLS / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*args: str) -> None:
    """Run an argument list without a shell and preserve tool failure codes."""
    subprocess.run(args, cwd=ROOT, check=True)


def setup() -> None:
    """Install pinned tools without changing the application environment."""
    target = tomllib.loads((ROOT / "ruff.toml").read_text())["target-version"]
    minimum = (int(target[2]), int(target[3:]))
    if sys.version_info[:2] < minimum:
        raise ValueError(f"Use Python {minimum[0]}.{minimum[1]} or newer for setup.")
    hooks_path = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if hooks_path.returncode not in (0, 1):
        raise ValueError("Cannot read Git hook settings. Is Git installed?")
    if hooks_path.returncode == 0:
        raise ValueError(
            "core.hooksPath is configured. Integrate pre-commit with your existing "
            "hook setup before continuing; this script will not change that setting."
        )
    if TOOLS.exists() and not (TOOLS / "pyvenv.cfg").is_file():
        raise ValueError(
            ".venv-tools exists but is not a virtual environment; leave it intact."
        )
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(TOOLS)
    run(str(PYTHON), "-m", "pip", "install", "-r", "requirements-dev.txt")
    run(str(PYTHON), "-m", "pre_commit", "validate-config")
    # Install environments up front so the first commit does not need downloads.
    # pre-commit's default migration mode preserves an existing custom hook.
    run(str(PYTHON), "-m", "pre_commit", "install", "--install-hooks")
    run(str(PYTHON), "-m", "ruff", "--version")
    run(str(PYTHON), "-m", "ruff", "check", ".")
    print("Setup complete. In VS Code run 'Ruff: Restart Server'.", flush=True)
    print("Safe lint fixes run on save. Review fixes before committing.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "check", "fix", "hooks"))
    action = parser.parse_args().action
    try:
        if action == "setup":
            setup()
        else:
            if not PYTHON.is_file():
                raise ValueError("Run 'python scripts/develop.py setup' first.")
            if action == "hooks":
                run(str(PYTHON), "-m", "pre_commit", "run", "--all-files")
            else:
                args = [str(PYTHON), "-m", "ruff", "check"]
                if action == "fix":
                    args.append("--fix")
                run(*args, ".")
    except subprocess.CalledProcessError as error:
        return error.returncode
    except (OSError, ValueError) as error:
        print(f"Developer tools: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
