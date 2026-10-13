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
    launches = json.loads((ROOT / ".vscode/launch.json").read_text())
    web = next(item for item in launches["configurations"] if item["name"] == "Day Ahead: web preview")
    assert web["module"] == "flask" and web["env"]["DAO_WEB_DATA_DIR"]
    # Execute the actual core launch arguments with its default input. VS Code
    # breakpoint interaction remains part of the manual acceptance checklist.
    core = next(item for item in launches["configurations"]
                if item["name"] == "Day Ahead: debug synthetic scenario")
    scenario = next(item["default"] for item in launches["inputs"] if item["id"] == "scenarioId")
    arguments = [argument.replace("${input:scenarioId}", scenario) for argument in core["args"]]
    core_environment = dict(os.environ)
    core_environment.update({key: value.replace("${workspaceFolder}", str(ROOT))
                             for key, value in core["env"].items()})
    result = subprocess.run(
        [str(python), "-m", core["module"], *arguments, "--json"],
        cwd=core["cwd"].replace("${workspaceFolder}", str(ROOT)),
        env=core_environment, capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["total"] == 1 and report["results"][0]["id"] == scenario
    assert report["results"][0]["status"] == "PASS", report
    print(f"Default core debug launch passed: {scenario}.")
    container = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text())
    assert container["build"]["dockerfile"] == "Dockerfile"
    assert "python scripts/setup_environment.py" in container["postCreateCommand"]
    assert container["forwardPorts"] == [5000, 5173]
    print("Dependency integrity, Ruff version, scenarios and web preview passed.")


if __name__ == "__main__":
    main()
