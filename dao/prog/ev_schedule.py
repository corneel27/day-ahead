"""Formatting helpers for EV charging schedules."""

import datetime as dt
from collections.abc import Sequence


def format_ev_charge_schedule(
    timestamps: Sequence[dt.datetime],
    consumption: Sequence[float],
    interval_seconds: int,
) -> str:
    """Return all contiguous EV charging periods as a human-readable string.

    ``timestamps`` contains the start time of each optimization interval and
    ``consumption`` its planned grid consumption.  A positive consumption marks
    a charging interval.  Every separate charging period is retained so a gap
    in the optimized schedule is never presented as continuous charging.
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if len(timestamps) != len(consumption):
        raise ValueError("timestamps and consumption must have the same length")

    periods: list[tuple[dt.datetime, dt.datetime]] = []
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None

    for timestamp, planned_consumption in zip(timestamps, consumption):
        if planned_consumption > 0:
            if period_start is None:
                period_start = timestamp
            period_end = timestamp + dt.timedelta(seconds=interval_seconds)
        elif period_start is not None:
            assert period_end is not None
            periods.append((period_start, period_end))
            period_start = None
            period_end = None

    if period_start is not None:
        assert period_end is not None
        periods.append((period_start, period_end))

    if not periods:
        return "Geen laadmomenten ingepland"

    def format_period(start: dt.datetime, end: dt.datetime) -> str:
        start_text = start.strftime("%d-%m %H:%M")
        end_text = (
            end.strftime("%H:%M")
            if start.date() == end.date()
            else end.strftime("%d-%m %H:%M")
        )
        return f"{start_text}\N{EN DASH}{end_text}"

    return ", ".join(format_period(start, end) for start, end in periods)
