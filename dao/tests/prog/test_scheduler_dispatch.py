"""Check schedule matching without waiting or starting application processes."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dao.prog import da_scheduler


class EndSchedulerIteration(Exception):
    """Stop the infinite scheduler after one complete dispatch iteration."""


@pytest.mark.parametrize("schedule,expected", [
    ({"0215": "exact"}, ["exact"]),
    ({"xx15": "minute"}, ["minute"]),
    ({"02xx": "hour"}, ["hour"]),
    ({"0214": "exact", "xx14": "minute", "03xx": "hour"}, []),
    ({"02xx": "hour", "0215": "exact", "xx15": "minute"}, ["hour", "exact", "minute"]),
    ({"0215": "exact", "xx15": "exact", "02xx": "exact"}, ["exact", "exact", "exact"]),
])
def test_schedule_patterns_preserve_dispatch_order_and_multiplicity(monkeypatch, schedule, expected):
    scheduler = da_scheduler.DaScheduler.__new__(da_scheduler.DaScheduler)
    scheduler.active = True
    scheduler.offset_start = 0
    scheduler.scheduler_tasks = schedule
    scheduler.tasks = {name: {"function": name} for name in ("exact", "minute", "hour")}
    scheduler.run_task_process = Mock(return_value=True)
    clock = Mock()
    clock.now.side_effect = [dt.datetime(2026, 1, 14, 2, 14),
                             dt.datetime(2026, 1, 14, 2, 15), EndSchedulerIteration()]
    monkeypatch.setattr(da_scheduler, "datetime", SimpleNamespace(datetime=clock, timedelta=dt.timedelta))
    monkeypatch.setattr(da_scheduler, "time", SimpleNamespace(sleep=Mock()))

    with pytest.raises(EndSchedulerIteration):
        scheduler.scheduler()

    assert [call.args[0] for call in scheduler.run_task_process.call_args_list] == expected


def test_hanging_task_is_killed_after_timeout(monkeypatch):
    proc = Mock()
    proc.wait.side_effect = [da_scheduler.TimeoutExpired("task", 1), None]
    monkeypatch.setattr(da_scheduler, "Popen", Mock(return_value=proc))
    scheduler = da_scheduler.DaScheduler.__new__(da_scheduler.DaScheduler)
    scheduler.tasks = {"calc": {"cmd": ["python3", "day_ahead.py", "calc"]}}

    assert scheduler.run_task_process("calc") is False
    proc.kill.assert_called_once_with()
    assert proc.wait.call_args_list[0].kwargs == {"timeout": da_scheduler.TASK_TIMEOUT}


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False)])
def test_finished_task_reports_exit_code(monkeypatch, returncode, expected):
    proc = Mock(returncode=returncode)
    monkeypatch.setattr(da_scheduler, "Popen", Mock(return_value=proc))
    scheduler = da_scheduler.DaScheduler.__new__(da_scheduler.DaScheduler)
    scheduler.tasks = {"calc": {"cmd": ["python3", "day_ahead.py", "calc"]}}

    assert scheduler.run_task_process("calc") is expected
    proc.kill.assert_not_called()
