import datetime as dt

import pytest

from dao.prog.ev_schedule import format_ev_charge_schedule


def test_formats_each_separate_charging_period():
    timestamps = [dt.datetime(2026, 7, 26, hour) for hour in range(5)]

    result = format_ev_charge_schedule(
        timestamps,
        [[0, 0], [0, 2.3], [0, 2.3], [0, 0], [0, 2.3]],
        [0, 2.3],
        [0, 10],
        dt.datetime(2026, 7, 26),
    )

    assert result == "26-07 01:00\N{EN DASH}03:00 (10 A), 26-07 04:00\N{EN DASH}05:00 (10 A)"


def test_formats_a_period_across_midnight_with_both_dates():
    timestamps = [
        dt.datetime(2026, 7, 26, 23, 30),
        dt.datetime(2026, 7, 26, 23, 45),
    ]

    result = format_ev_charge_schedule(
        timestamps,
        [[0, 0.6], [0, 0.6]],
        [0, 2.4],
        [0, 10],
        dt.datetime(2026, 7, 26),
    )

    assert result == "26-07 23:30\N{EN DASH}27-07 00:00 (10 A)"


def test_formats_the_real_partial_interval_end_time():
    timestamps = [dt.datetime(2026, 7, 26, hour) for hour in range(14, 17)]

    result = format_ev_charge_schedule(
        timestamps,
        [[0, 2.576], [0, 11.04], [0, 1.472]],
        [0, 11.04],
        [0, 16],
        dt.datetime(2026, 7, 26, 14, 46),
    )

    assert result == "26-07 14:46\N{EN DASH}16:08 (16 A)"


def test_reports_when_no_charging_is_planned():
    timestamps = [dt.datetime(2026, 7, 26, hour) for hour in range(2)]

    result = format_ev_charge_schedule(
        timestamps,
        [[0, 0], [0, 0]],
        [0, 2.3],
        [0, 10],
        dt.datetime(2026, 7, 26),
    )

    assert result == "Geen laadmomenten ingepland"


@pytest.mark.parametrize(
    ("timestamps", "stage_energy", "stage_powers", "stage_amperes"),
    [([], [[1]], [1], [1]), ([], [], [1], [])],
)
def test_rejects_invalid_schedule_input(
    timestamps, stage_energy, stage_powers, stage_amperes
):
    with pytest.raises(ValueError):
        format_ev_charge_schedule(
            timestamps,
            stage_energy,
            stage_powers,
            stage_amperes,
            dt.datetime(2026, 7, 26),
        )
