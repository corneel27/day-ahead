"""Verify module logs still reach the configured task outputs and exceptions."""

import datetime as dt
import importlib
import logging
from unittest.mock import Mock

import pytest

from dao.lib import da_meteo, da_prices, db_manager
from dao.prog.da_base import DaBase
from dao.prog.scenarios.runner import _capture_root_log


@pytest.fixture
def root_logging(monkeypatch):
    root = logging.getLogger()
    previous_level = root.level
    monkeypatch.setattr(root, "handlers", [])
    root.setLevel(logging.INFO)
    try:
        yield root
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(previous_level)


@pytest.mark.parametrize("level", [logging.INFO, logging.WARNING])
@pytest.mark.parametrize("fail", [False, True])
def test_task_logging_preserves_file_console_notifications_and_exit_code(
    monkeypatch, tmp_path, capsys, root_logging, level, fail,
):
    (tmp_path / "prog").mkdir()
    log_dir = tmp_path / "data" / "log"
    log_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "prog")
    root_logging.setLevel(level)
    notify = Mock()
    monkeypatch.setattr("hassapi.Hass.set_value", notify)
    task = DaBase.__new__(DaBase)
    task.tasks = {"test": {"function": "execute", "file_name": "test"}}
    task.log_level = level
    task.notification_entity = "input_text.test_notification"
    task.db_da = Mock()
    task.start_logging = Mock()
    task.set_last_activity = Mock()

    def execute():
        da_meteo._LOGGER.debug("Hidden task debug")
        da_meteo._LOGGER.info("Task details")
        db_manager._LOGGER.warning("Task warning")
        if fail:
            raise ValueError("synthetic task failure")
        da_prices._LOGGER.error("Task error")

    task.execute = execute
    assert task.run_task_function("test") == int(fail)
    log_files = list(log_dir.glob("test_*.log"))
    assert len(log_files) == 1
    text = log_files[0].read_text()
    assert capsys.readouterr().out == text
    assert "Hidden task debug" not in text
    assert ("Task details" in text) is (level == logging.INFO)
    assert text.count("Task warning") == 1
    assert notify.call_count == 2
    assert notify.call_args_list[0].args[0] == "input_text.test_notification"
    assert notify.call_args_list[0].args[1].endswith("Task warning")
    if fail:
        assert "Traceback (most recent call last)" in text
        assert text.count("ValueError: synthetic task failure") == 1
        assert "Task error" not in text
        task.set_last_activity.assert_not_called()
    else:
        assert text.count("Task error") == 1
        assert "Traceback" not in text
        task.set_last_activity.assert_called_once_with()


@pytest.mark.parametrize("module_name", [
    "dao.lib.da_meteo", "dao.lib.da_prices", "dao.lib.db_manager",
    "dao.prog.da_base", "dao.prog.da_report", "dao.prog.da_scheduler",
    "dao.prog.day_ahead", "dao.prog.scenarios.parsing", "dao.prog.solar_predictor",
    "dao.prog.utils",
])
def test_scenario_capture_receives_module_source_once(module_name, root_logging):
    logger = importlib.import_module(module_name)._LOGGER
    assert logger.name == module_name
    assert logger.level == logging.NOTSET
    assert logger.propagate
    assert not logger.handlers
    previous_handlers = root_logging.handlers[:]
    stop = _capture_root_log()
    try:
        logger.info("EV setup echo retained")
    finally:
        captured = stop()
    assert captured == "EV setup echo retained\n"
    assert root_logging.level == logging.INFO
    assert root_logging.handlers == previous_handlers


def test_nordpool_failure_keeps_traceback_context_and_returns_none(monkeypatch, caplog):
    date = dt.datetime(2026, 1, 14, tzinfo=dt.UTC)
    client = Mock()
    client.fetch.side_effect = RuntimeError("synthetic provider failure")
    monkeypatch.setattr(da_prices, "NordpoolPrices", Mock(return_value=client))
    prices = da_prices.DaPrices.__new__(da_prices.DaPrices)
    prices.country = "NL"
    with caplog.at_level(logging.ERROR):
        assert prices._get_prices_nordpool(60, date) is None
    records = [record for record in caplog.records if record.name == "dao.lib.da_prices"]
    assert len(records) == 2
    assert [record.levelno for record in records] == [logging.ERROR, logging.ERROR]
    assert "Nordpool" in records[0].getMessage()
    assert str(date) in records[0].getMessage()
    assert "synthetic provider failure" not in records[0].getMessage()
    assert records[0].exc_info[0] is RuntimeError
    assert str(records[0].exc_info[1]) == "synthetic provider failure"
    assert "RuntimeError: synthetic provider failure" in caplog.text
    assert records[1].getMessage() == f"Fout bij ophalen data van Nordpool voor {date}"
