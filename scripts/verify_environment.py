"""Smoke-test the installed development environment, including the web preview."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    python = ROOT / ".venv/bin/python"
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "dao/prog"))),
                       DAO_WEB_DATA_DIR=str(ROOT / ".local/web-data"), TZ="UTC", MPLBACKEND="Agg")
    environment.pop("VITE_DEV", None)
    subprocess.run([str(python), "-m", "pip", "check"], check=True)
    subprocess.run([str(python), "scripts/develop.py", "status"], cwd=ROOT, check=True)
    subprocess.run([str(python), "-m", "dao.prog.da_debug", "scenario-validate"],
                   cwd=ROOT, env=environment, check=True)
    # Load real routes, templates, configuration and the built Vite manifest.
    # No mocked application startup: missing dependencies or config fail here.
    subprocess.run([str(python), "-c", """
from app import app
client = app.test_client()
for path in ('/', '/v2/chart', '/v2/config'):
    response = client.get(path, follow_redirects=True)
    assert response.status_code == 200, (path, response.status_code)
    assert b'/static/build/' in response.data, path
"""], cwd=ROOT / "dao/webserver", env=environment, check=True)
    launch = json.loads((ROOT / ".vscode/launch.json").read_text())["configurations"][0]
    assert launch["module"] == "flask" and launch["env"]["DAO_WEB_DATA_DIR"]
    print("Dependency integrity, Ruff version, scenarios and web preview passed.")


if __name__ == "__main__":
    main()
