"""Smoke-test the installed development environment, including the web preview."""

import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class FrontendLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        url = None
        if tag == "script":
            url = attributes.get("src")
        elif tag == "link" and attributes.get("rel") in ("stylesheet", "modulepreload"):
            url = attributes.get("href")
        if url and url.startswith("/static/build/"):
            self.urls.add(url)


def verify_frontend_assets(client):
    """Check the built frontend through Flask, including CSS-referenced icon fonts."""
    urls = set()
    for path in ("/", "/v2/chart", "/v2/config"):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200, (path, response.status_code)
        links = FrontendLinks()
        links.feed(response.get_data(as_text=True))
        assert links.urls, f"No built frontend assets in {path}"
        urls.update(links.urls)
    stylesheets = 0
    scripts = 0
    icon_fonts = set()
    for url in sorted(urls):
        response = client.get(url)
        assert response.status_code == 200 and response.data, (url, response.status_code)
        suffix = Path(urlsplit(url).path).suffix
        if suffix == ".js":
            scripts += 1
            assert response.mimetype in ("text/javascript", "application/javascript"), url
        elif suffix == ".css":
            stylesheets += 1
            assert response.mimetype == "text/css", url
            for reference in re.findall(r"url\(\s*['\"]?([^'\"\s)]+)", response.get_data(as_text=True)):
                if "bootstrap-icons" in reference and Path(urlsplit(reference).path).suffix in (".woff", ".woff2"):
                    font_url = urljoin(url, reference)
                    assert not urlsplit(font_url).netloc, font_url
                    font = client.get(font_url)
                    assert font.status_code == 200, (font_url, font.status_code)
                    assert font.data[:4] in (b"wOFF", b"wOF2"), font_url
                    icon_fonts.add(font_url)
    assert scripts and stylesheets and icon_fonts, "Missing built JavaScript, CSS or Bootstrap icon fonts"
    print(f"Built frontend: {scripts} scripts, {stylesheets} stylesheets and {len(icon_fonts)} icon fonts served.")


def main() -> None:
    subprocess.run(["node", str(ROOT / "scripts/verify_node_runtime.mjs")], check=True)
    subprocess.run(["node", "--test", str(ROOT / "scripts/verify_node_runtime.test.mjs")], check=True)
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
from scripts.verify_environment import verify_frontend_assets
client = app.test_client()
verify_frontend_assets(client)
# Preview tasks must never fall back to the ordinary dao/data installation.
assert client.post('/v2/task-exec', data={'task': 'clean_data'}).status_code == 403
assert client.get('/api/run/clean_data').status_code == 403
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
    assert "sh script/setup" in container["postCreateCommand"]
    assert container["waitFor"] == "postCreateCommand"
    assert container["forwardPorts"] == [5000, 5173]
    print("Dependency integrity, Ruff version, scenarios and web preview passed.")


if __name__ == "__main__":
    main()
