"""Check the real task worker with deterministic process and state IO."""
import importlib
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def run_worker(monkeypatch, tmp_path):
    # Match the route tests' isolated startup; importing Flask must not load a
    # user's configuration, open their log or connect to Home Assistant.
    monkeypatch.setenv("DAO_WEB_DATA_DIR", str(tmp_path))
    with patch("dao.prog.config.loader.ConfigurationLoader.load_and_validate", return_value=None), \
            patch("logging.handlers.TimedRotatingFileHandler", return_value=logging.NullHandler()):
        routes = importlib.import_module("dao.webserver.app.v2.routes")
    monkeypatch.setattr(routes, "app_datapath", str(tmp_path))
    monkeypatch.setattr(routes, "get_file_list_with_ts", lambda *args: [])
    monkeypatch.setattr(routes, "time", SimpleNamespace(sleep=lambda seconds: None))

    def run(polls, *, requested="running", kill_code=-9, has_log=True, replacement=False):
        logfile = tmp_path / "original.log"
        logfile.write_text("original task output")
        original = {"task": "original", "status": "running", "logfile": str(logfile) if has_log else None}
        stored = dict(original, status=requested)
        replacement_log = tmp_path / "replacement.log"
        if replacement:
            replacement_log.write_text("replacement task output")
            stored.update(task="replacement", logfile=str(replacement_log))
        before = stored.copy()
        saved = []
        process = Mock(spec=["poll", "kill", "wait", "returncode"])
        process.returncode = None
        results = iter(polls)

        def poll():
            result = next(results)
            if result is not None:
                process.returncode = result
            return result

        def kill():
            process.returncode = kill_code

        def wait():
            assert process.returncode is not None, "Fixture process has not completed"
            return process.returncode

        def save(value):
            if value["status"] in {"cancelled", "done", "error"}:
                assert process.wait.called, "A terminal status must follow process reaping"
            stored.clear()
            stored.update(value)
            saved.append(value.copy())

        process.poll.side_effect = poll
        process.kill.side_effect = kill
        process.wait.side_effect = wait
        popen = Mock(return_value=process)
        monkeypatch.setattr(routes, "Popen", popen)
        monkeypatch.setattr(routes, "get_task_state", lambda: stored.copy())
        monkeypatch.setattr(routes, "save_task_state", save)
        routes.run_and_log(["synthetic-task"], original.copy())
        popen.assert_called_once()
        assert process.wait.called
        return SimpleNamespace(process=process, state=stored, before=before, saved=saved,
                               logfile=logfile, replacement_log=replacement_log)

    return run


@pytest.mark.parametrize("has_log", [True, False], ids=["with-log", "without-log"])
def test_cancelled_process_keeps_cancelled_status(run_worker, has_log):
    result = run_worker([None, None], requested="cancelled", has_log=has_log)
    assert result.state["status"] == "cancelled"
    assert result.state["returncode"] == -9
    result.process.kill.assert_called_once()
    if has_log:
        assert not result.logfile.exists()


@pytest.mark.parametrize(("code", "status"), [(0, "done"), (7, "error")])
def test_normal_completion_preserves_exit_status_and_log(run_worker, code, status):
    result = run_worker([None, code])
    assert result.state["status"] == status
    assert result.state["returncode"] == code
    assert result.logfile.read_text() == "original task output"
    result.process.kill.assert_not_called()


@pytest.mark.parametrize(("code", "status"), [(0, "done"), (7, "error")])
def test_process_finishing_before_cancel_is_not_reported_as_cancelled(run_worker, code, status):
    result = run_worker([None, code], requested="cancelled")
    assert result.state["status"] == status
    assert result.state["returncode"] == code
    assert result.logfile.read_text() == "original task output"
    result.process.kill.assert_not_called()


def test_process_finishing_during_kill_preserves_success_and_log(run_worker):
    result = run_worker([None, None], requested="cancelled", kill_code=0)
    assert result.state["status"] == "done"
    assert result.state["returncode"] == 0
    assert result.logfile.read_text() == "original task output"
    result.process.kill.assert_called_once()


def test_cancellation_after_process_completion_preserves_success(run_worker):
    result = run_worker([0], requested="cancelled")
    assert result.state["status"] == "done"
    assert result.state["returncode"] == 0
    assert result.logfile.exists()
    result.process.kill.assert_not_called()


def test_replacement_task_state_and_log_are_not_overwritten(run_worker):
    result = run_worker([None], replacement=True)
    assert result.state == result.before
    assert result.saved == []
    assert result.replacement_log.read_text() == "replacement task output"
    assert not result.logfile.exists()
    result.process.kill.assert_called_once()
