"""Exercise the reported route vulnerabilities through Flask requests."""
import importlib
import logging
from unittest.mock import Mock, patch

import pytest

# V1 reads configuration and opens a log at import time. Keep those startup
# effects isolated from the route tests and the user's actual data.
with patch("dao.prog.config.loader.ConfigurationLoader.load_and_validate", return_value=None), \
        patch("logging.handlers.TimedRotatingFileHandler", return_value=logging.NullHandler()):
    from dao.webserver.app import app

api_routes = importlib.import_module("dao.webserver.app.api.routes")
v2_routes = importlib.import_module("dao.webserver.app.v2.routes")


@pytest.fixture
def client():
    return app.test_client()


def test_unknown_task_is_escaped_plain_text(client):
    response = client.get("/api/run/%3Cimg%20src=x%20onerror=alert(1)%3E")
    assert response.status_code == 400
    assert response.mimetype == "text/plain"
    assert b"<img" not in response.data


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
