"""Naive local report times around the daylight saving time changes."""
import pandas as pd

from dao.prog.utils import localize_local_times

TZ = "Europe/Amsterdam"


def _times(*values):
    return pd.Series(pd.to_datetime(list(values)))


def test_repeated_hour_at_end_of_dst_gets_both_offsets():
    times = _times("2026-10-25 01:45", "2026-10-25 02:00", "2026-10-25 02:45",
                   "2026-10-25 02:00", "2026-10-25 02:45", "2026-10-25 03:00")
    result = localize_local_times(times, TZ)
    offsets = [ts.utcoffset().total_seconds() / 3600 for ts in result]
    assert offsets == [2, 2, 2, 1, 1, 1]
    assert result.is_monotonic_increasing


def test_single_occurrence_of_the_repeated_hour_is_summer_time():
    # uurwaarden: 02:00 maar een keer, bijvoorbeeld een prognose per uur
    result = localize_local_times(_times("2026-10-25 01:00", "2026-10-25 02:00",
                                         "2026-10-25 03:00"), TZ)
    assert [ts.utcoffset().total_seconds() / 3600 for ts in result] == [2, 2, 1]


def test_missing_hour_at_start_of_dst_moves_forward():
    result = localize_local_times(_times("2026-03-29 01:00", "2026-03-29 02:00"), TZ)
    assert result.iloc[1] == pd.Timestamp("2026-03-29 03:00", tz=TZ)


def test_index_with_duplicates_is_kept():
    times = _times("2026-10-24 10:00", "2026-10-24 11:00")
    times.index = [5, 5]
    result = localize_local_times(times, TZ)
    assert list(result.index) == [5, 5]
    assert result.iloc[0] == pd.Timestamp("2026-10-24 10:00", tz=TZ)
