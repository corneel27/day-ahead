"""Set up the Linux application environment and the shared Ruff tools."""

import json
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
DATA = ROOT / ".local" / "web-data"


def run(*args: str, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def prepare_preview() -> None:
    """Create separate preview files, preserving edits on subsequent setup runs."""
    for directory in (DATA, DATA / "images", DATA / "log"):
        directory.mkdir(parents=True, exist_ok=True)
    options = DATA / "options.json"
    if not options.exists():
        content = json.loads((ROOT / "dao/data/options_example.json").read_text())
        content["homeassistant"] = {"host": "127.0.0.1", "ip port": 8123}
        # Example configuration has no credentials: do not copy a user's secrets.
        options.write_text(json.dumps(content, indent=2) + "\n")
    secrets = DATA / "secrets.json"
    if not secrets.exists():
        secrets.write_text("{}\n")


def main() -> None:
    if sys.platform != "linux":
        raise SystemExit("Use the VS Code Dev Container or Linux/WSL for the application environment.")
    if sys.version_info < (3, 12):  # noqa: UP036 -- bootstrap may run before selecting the project interpreter
        raise SystemExit("Python 3.12 or newer is required; the Dev Container provides Python 3.14.")
    if not PYTHON.exists():
        if (ROOT / ".venv").exists():
            raise SystemExit("Existing .venv is not a Linux environment. Use a separate checkout or recreate it explicitly.")
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    run(str(PYTHON), "-m", "pip", "install", "-r", "dao/requirements.txt", "-r", "requirements-test.txt")
    run(str(PYTHON), "-m", "pip", "check")
    run("npm", "ci", cwd=ROOT / "dao/webserver")
    run("npm", "run", "build", cwd=ROOT / "dao/webserver")
    prepare_preview()
    run(str(PYTHON), "scripts/develop.py", "setup")
    print("Development environment is ready. Next step: press F5 with 'Day Ahead: web preview' selected to open the application.")


if __name__ == "__main__":
    main()
