from hassapi.exceptions import ClientError, Unauthorised
from requests.exceptions import ConnectTimeout

from dao.webserver.app import app
from dao.webserver.app.v2 import routes


def test_reports_shows_authentication_error(monkeypatch):
    def reject_credentials(*args, **kwargs):
        raise Unauthorised("401 from Home Assistant")

    monkeypatch.setattr(routes, "reports_gen", reject_credentials)
    monkeypatch.setenv("VITE_DEV", "1")

    response = app.test_client().get("/v2/reports")

    assert response.status_code == 503
    assert b"Home Assistant rejected the API credentials" in response.data
    assert b"Traceback" not in response.data


def test_reports_shows_connection_error(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ClientError("Home Assistant API is not running.")

    monkeypatch.setattr(routes, "reports_gen", unavailable)
    monkeypatch.setenv("VITE_DEV", "1")

    response = app.test_client().get("/v2/reports")

    assert response.status_code == 503
    assert b"Check the Home Assistant address and availability" in response.data
    assert b"Traceback" not in response.data


def test_reports_shows_connection_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise ConnectTimeout("Connection timed out")

    monkeypatch.setattr(routes, "Report", timeout)
    monkeypatch.setenv("VITE_DEV", "1")

    response = app.test_client().get("/v2/reports")

    assert response.status_code == 503
    assert b"Check the Home Assistant address and availability" in response.data
    assert b"Traceback" not in response.data
