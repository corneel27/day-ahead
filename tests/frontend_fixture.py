"""Serve real task routes and built assets with an in-memory task backend."""

import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="dao-browser-") as directory:
        data = Path(directory)
        (data / "log").mkdir()
        (data / "images").mkdir()
        options = json.loads((ROOT / "dao/data/options_example.json").read_text())
        options["homeassistant"] = {"host": "127.0.0.1", "ip port": 8123}
        (data / "options.json").write_text(json.dumps(options))
        (data / "secrets.json").write_text("{}")
        os.chdir(ROOT / "dao/webserver")
        os.environ["DAO_WEB_DATA_DIR"] = str(data)
        os.environ.pop("VITE_DEV", None)
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "dao/prog"))
        app = importlib.import_module("dao.webserver.app").app
        routes = importlib.import_module("dao.webserver.app.v2.routes")
        constants = importlib.import_module("dao.prog.da_const")
        flask = importlib.import_module("flask")
        state = {"status": "idle", "task": "synthetic"}
        polls = 0

        def get_state():
            nonlocal polls
            if state["status"] == "running":
                polls += 1
                if state["task"] == "complete" and polls >= 3:
                    state.update(status="completed", returncode=0, last_update=time.time())
            return state.copy()

        def save_state(value):
            nonlocal polls
            state.clear()
            state.update(value)
            polls = 0

        def forbid_process(*args, **kwargs):
            raise AssertionError("Browser fixtures must never launch task processes")

        class SyntheticThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                pass

        routes.get_task_state = get_state
        routes.save_task_state = save_state
        routes.threading = SimpleNamespace(Thread=SyntheticThread)
        routes.run_and_log = forbid_process
        routes.Popen = forbid_process
        constants.tasks = {
            "complete": {"name": "Run synthetic task", "cmd": ["never", "never"], "ui_enabled": True},
            "waiting": {"name": "Run cancellable task", "cmd": ["never", "never"], "ui_enabled": True},
        }
        # Only this isolated fixture enables task routes; all task IO above is
        # replaced before serving. Production preview protections stay intact.
        app.config["DAO_WEB_PREVIEW"] = False

        @app.before_request
        def restrict_fixture_routes():
            if flask.request.endpoint == "v2.tasks":
                save_state({"status": "idle", "task": "synthetic"})
            if flask.request.endpoint not in {
                "v2.tasks", "v2.task_exec", "v2.task_state", "v2.task_cancel", "static",
            }:
                flask.abort(404)
            if flask.request.endpoint == "static" and not flask.request.path.startswith("/static/build/"):
                flask.abort(404)

        app.run(host="127.0.0.1", port=8765, debug=False)


if __name__ == "__main__":
    main()
