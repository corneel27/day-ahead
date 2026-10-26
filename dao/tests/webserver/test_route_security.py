"""Exercise the reported route vulnerabilities through Flask requests."""
import importlib
import json
import logging
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from hassapi.exceptions import ClientError as HassClientError
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.exc import OperationalError

# V1 reads configuration and opens a log at import time. Keep those startup
# effects isolated from the route tests and the user's actual data.
with patch("dao.prog.config.loader.ConfigurationLoader.load_and_validate", return_value=None), \
        patch("logging.handlers.TimedRotatingFileHandler", return_value=logging.NullHandler()):
    from dao.webserver.app import app

api_routes = importlib.import_module("dao.webserver.app.api.routes")
v2_routes = importlib.import_module("dao.webserver.app.v2.routes")
v1_routes = importlib.import_module("dao.webserver.app.v1.routes")


@pytest.mark.parametrize("age", [599, 600, 601])
def test_running_task_expires_only_after_cutoff(monkeypatch, tmp_path, age):
    state_file = tmp_path / "task_state.json"
    state = {"status": "running", "task": "calculate", "logfile": "test.log",
             "last_update": 1000 - age}
    state_file.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(v1_routes, "STATEFILE", str(state_file))
    monkeypatch.setattr(v1_routes, "STALE_AFTER", 600)
    monkeypatch.setattr(v1_routes.time, "time", lambda: 1000)

    expected = {"status": "idle", "task": None, "logfile": None} if age > 600 else state
    assert v1_routes.load_state() == expected


@pytest.mark.parametrize("status", ["idle", "done", "failed"])
def test_non_running_state_does_not_evaluate_missing_timestamp(monkeypatch, tmp_path, status):
    state_file = tmp_path / "task_state.json"
    state = {"status": status, "task": "calculate", "last_update": None}
    state_file.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(v1_routes, "STATEFILE", str(state_file))
    assert v1_routes.load_state() == state


@pytest.mark.parametrize("contents", [None, "invalid json"])
def test_unavailable_task_state_falls_back_to_idle(monkeypatch, tmp_path, contents):
    state_file = tmp_path / "task_state.json"
    if contents is not None:
        state_file.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(v1_routes, "STATEFILE", str(state_file))
    result = v1_routes.load_state()
    assert result["status"] == "idle"
    assert result["task"] is None


@pytest.mark.parametrize("solar_present", [False, True])
def test_solar_menu_can_be_removed_repeatedly_and_restored(monkeypatch, solar_present):
    keys = ("home", "run", "reports", "savings", "solar", "settings")
    menu = {key: {"name": key} for key in keys if solar_present or key != "solar"}
    other_items = {key: value for key, value in menu.items() if key != "solar"}
    monkeypatch.setattr(v1_routes, "web_menu", menu)
    monkeypatch.setattr(v1_routes, "solar_web_menu", deepcopy(v1_routes.solar_web_menu))
    solar = SimpleNamespace(name="roof", ml_prediction=False)
    monkeypatch.setattr(v1_routes, "config", SimpleNamespace(solar=[solar], battery=[]))

    for _ in range(2):
        assert v1_routes.generate_solar_items() == {}
        assert v1_routes.web_menu == other_items

    solar.ml_prediction = True
    for _ in range(2):
        assert v1_routes.generate_solar_items() == {"roof": solar}
        assert tuple(v1_routes.web_menu) == keys
        assert {key: value for key, value in v1_routes.web_menu.items() if key != "solar"} == other_items


@pytest.fixture
def client():
    return app.test_client()


@pytest.mark.parametrize(("dim", "stepped"), [("kWh", False), ("euro/kWh", True)])
def test_datasets_config_reflects_variable_table(monkeypatch, dim, stepped):
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    variables = Table(
        "variabel", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String), Column("code", String), Column("dim", String),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(variables.insert(), {"id": 1, "name": "Consumption", "code": "cons", "dim": dim})
    report = Mock()
    report.db_da.metadata = MetaData()
    report.db_da.engine = engine
    monkeypatch.setattr(v2_routes, "Report", Mock(return_value=report))
    try:
        datasets = v2_routes._datasets_config()
        assert len(datasets) == 1
        assert datasets[0]["label"] == "Consumption"
        assert datasets[0]["code"] == "cons"
        assert datasets[0]["stepped"] is stepped
    finally:
        engine.dispose()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("task", ["calc_optimum", "calc", "calc_zonder_debug"])
def test_api_task_and_aliases_execute_exactly_once(client, monkeypatch, tmp_path, method, task):
    program_dir = tmp_path / "prog"
    program_dir.mkdir()
    log_dir = tmp_path / "data" / "log"
    log_dir.mkdir(parents=True)
    monkeypatch.chdir(program_dir)
    monkeypatch.setitem(app.config, "DAO_WEB_PREVIEW", False)
    monkeypatch.setattr(api_routes, "PROG_DIR", program_dir)
    runner = Mock(return_value=SimpleNamespace(stdout="task output\n", stderr="task warning\n"))
    monkeypatch.setattr(api_routes, "subprocess_run", runner)

    response = client.open(f"/api/run/{task}", method=method)

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.data == b"task output\ntask warning\n"
    runner.assert_called_once_with(
        api_routes.tasks["calc_optimum"]["cmd"], cwd=program_dir, capture_output=True, text=True,
    )
    logs = list(log_dir.glob("calc_*.log"))
    assert len(logs) == 1
    assert logs[0].read_text() == "task output\ntask warning\n"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unknown_task_is_escaped_plain_text(client, monkeypatch, method):
    runner = Mock(side_effect=AssertionError("Unknown task must not execute a command"))
    monkeypatch.setattr(api_routes, "subprocess_run", runner)
    response = client.open("/api/run/%3Cimg%20src=x%20onerror=alert(1)%3E", method=method)
    assert response.status_code == 400
    assert response.mimetype == "text/plain"
    assert b"<img" not in response.data
    runner.assert_not_called()


@pytest.mark.parametrize("filename", [None, "../options.json", "/tmp/private.log", "..\\private.log", "file\x00.log"])
def test_log_rejects_invalid_paths(client, filename):
    response = client.get("/v2/view-file", query_string={} if filename is None else {"file": filename})
    assert response.status_code == 400


def test_log_rejects_symlink_escape(client, monkeypatch, tmp_path):
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    secret = tmp_path / "secret.log"
    secret.write_text("private")
    (log_dir / "outside.log").symlink_to(secret)
    monkeypatch.setattr(v2_routes, "app_datapath", str(tmp_path))
    response = client.get("/v2/view-file", query_string={"file": "outside.log"})
    assert response.status_code == 400
    assert b"private" not in response.data


def test_log_valid_and_missing_files(client, monkeypatch, tmp_path):
    (tmp_path / "log").mkdir()
    (tmp_path / "log" / "task.log").write_text("normal log")
    monkeypatch.setattr(v2_routes, "app_datapath", str(tmp_path))
    monkeypatch.setattr(v2_routes, "render_template", lambda template, **kwargs: kwargs["content"])
    assert client.get("/v2/view-file?file=task.log").data == b"normal log"
    assert client.get("/v2/view-file?file=missing.log").status_code == 404


def test_data_errors_hide_exception_details(client, monkeypatch):
    report = Mock()
    report.get_data.side_effect = RuntimeError("secret database path and credentials")
    monkeypatch.setattr(api_routes, "Report", Mock(return_value=report))
    response = client.get("/api/data/?start=2026-01-14&end=2026-01-15&aggregate=hour")
    assert response.status_code == 500
    assert b"secret" not in response.data
    assert response.json == {"error": "Gegevens konden niet worden opgehaald"}


@pytest.mark.parametrize("query", ["", "start=bad&end=2026-01-15", "start=2026-01-14&end=2026-01-15&timezone=invalid"])
def test_bad_data_dates_are_client_errors(client, query):
    response = client.get("/api/data/?aggregate=hour&" + query)
    assert response.status_code == 400


@pytest.mark.parametrize("method,path,data", [
    ("POST", "/v2/task-exec", {"task": "clean_data"}),
    ("GET", "/v2/task-cancel", {}),
    ("GET", "/v2/task-state", {}),
    ("GET", "/v2/tasks", {}),
    ("GET", "/api/run/clean_data", {}),
    ("POST", "/api/run/clean_data", {}),
    ("POST", "/v1/run", {"current_bewerking": "clean_data"}),
    ("GET", "/v1/run", {"current_bewerking": "clean_data"}),
    ("POST", "/v1/", {"current_menu": "run", "current_bewerking": "clean_data"}),
    ("POST", "/v1/", {"current_menu": "run"}),
    ("POST", "/v1/", {"menu_run": "Run"}),
    ("GET", "/v1/status", {}),
    ("GET", "/v1/log", {}),
])
def test_preview_blocks_live_tasks_and_shared_state(client, monkeypatch, method, path, data):
    v1_routes = importlib.import_module("dao.webserver.app.v1.routes")
    monkeypatch.setitem(app.config, "DAO_WEB_PREVIEW", True)
    live_calls = [
        (api_routes, "subprocess_run"),
        (v2_routes, "get_task_state"),
        (v2_routes, "Popen"),
        (v1_routes, "load_state"),
        (v1_routes, "Popen"),
    ]
    mocks = []
    for module, name in live_calls:
        blocked = Mock(side_effect=AssertionError("Preview accessed live task execution/state"))
        monkeypatch.setattr(module, name, blocked)
        mocks.append(blocked)
    response = client.open(path, method=method, data=data)
    assert response.status_code == 403
    assert response.mimetype == "text/plain"
    assert b"synthetic scenario" in response.data
    for blocked in mocks:
        blocked.assert_not_called()


@pytest.mark.parametrize(("error", "status"), [
    (requests.ConnectionError("no route to host"), 503),
    (OperationalError("SELECT 1", {}, Exception("lost connection")), 503),
    (HassClientError("Home Assistant API is not running."), 503),
    (KeyError("secret database path"), 500),
])
def test_report_errors_are_json(client, monkeypatch, error, status):
    monkeypatch.setattr(api_routes, "Report", Mock(side_effect=error))
    response = client.get("/api/report/consumption/vandaag_en_morgen")
    assert response.status_code == status
    assert response.json["message"] == "Failed"
    assert b"secret" not in response.data


def test_report_returns_data(client, monkeypatch):
    report = Mock()
    report.get_api_data.return_value = '{ "message":"Success", "data": [] }'
    monkeypatch.setattr(api_routes, "Report", Mock(return_value=report))
    response = client.get("/api/report/consumption/vandaag_en_morgen?cumulate=1")
    assert response.status_code == 200
    assert response.json == {"message": "Success", "data": []}
    report.get_api_data.assert_called_once_with(
        "consumption", "vandaag_en_morgen", cumulate=True
    )
