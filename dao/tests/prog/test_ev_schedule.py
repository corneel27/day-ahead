import datetime as dt

import pytest

from dao.prog.ev_schedule import format_ev_charge_schedule


def test_formats_each_separate_charging_period():
    timestamps = [dt.datetime(2026, 7, 26, hour) for hour in range(5)]

    result = format_ev_charge_schedule(timestamps, [0, 2.3, 2.3, 0, 2.3], 3600)

    assert result == "26-07 01:00\N{EN DASH}03:00, 26-07 04:00\N{EN DASH}05:00"


def test_formats_a_period_across_midnight_with_both_dates():
    timestamps = [
        dt.datetime(2026, 7, 26, 23, 30),
        dt.datetime(2026, 7, 26, 23, 45),
    ]

    result = format_ev_charge_schedule(timestamps, [1.2, 1.2], 900)

    assert result == "26-07 23:30\N{EN DASH}27-07 00:00"


def test_reports_when_no_charging_is_planned():
    timestamps = [dt.datetime(2026, 7, 26, hour) for hour in range(2)]

    result = format_ev_charge_schedule(timestamps, [0, 0], 3600)

    assert result == "Geen laadmomenten ingepland"


@pytest.mark.parametrize(
    ("timestamps", "consumption", "interval_seconds"),
    [([], [1], 3600), ([], [], 0)],
)
def test_rejects_invalid_schedule_input(timestamps, consumption, interval_seconds):
    with pytest.raises(ValueError):
        format_ev_charge_schedule(timestamps, consumption, interval_seconds)
