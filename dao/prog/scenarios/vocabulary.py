"""The small declarative vocabulary a scenario JSON uses.

S1 scope: parse the ``start`` anchor and expand the hourly ``prices`` /
``solar`` / ``baseload`` / ``temp`` arrays to the 15-minute model grid.
Time *offsets* (``"+8h"``) and the plugin escape hatch arrive with the EV
port in S2.
"""

from __future__ import annotations

import datetime as dt

INTERVAL_MIN = 15
STEPS_PER_HOUR = 60 // INTERVAL_MIN  # 4


class VocabularyError(ValueError):
    """A scenario field the vocabulary cannot make sense of."""


def parse_start(value: str) -> dt.datetime:
    """``"YYYY-MM-DD HH:MM"`` (or with seconds) -> naive datetime on a
    15-minute boundary. Anything off the grid is a hard error rather than a
    silent round, because the price/solar arrays are indexed from here."""
    if not isinstance(value, str):
        raise VocabularyError(f"start must be a string, got {value!r}")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    else:
        raise VocabularyError(f"start {value!r} is not 'YYYY-MM-DD HH:MM'")
    if parsed.minute % INTERVAL_MIN or parsed.second:
        raise VocabularyError(
            f"start {value!r} must land on a {INTERVAL_MIN}-minute boundary"
        )
    return parsed


def upsample(hourly: list[float], horizon_hours: int, *, label: str) -> list[float]:
    """Repeat each hourly value ``STEPS_PER_HOUR`` times to reach the model
    grid. Shorter than the horizon is an error naming the shortfall; longer
    is truncated."""
    if not isinstance(hourly, (list, tuple)) or not hourly:
        raise VocabularyError(f"{label} must be a non-empty list of numbers")
    try:
        vals = [float(x) for x in hourly]
    except (TypeError, ValueError) as ex:
        raise VocabularyError(f"{label} contains a non-number: {ex}") from ex
    if len(vals) < horizon_hours:
        raise VocabularyError(
            f"{label} has {len(vals)} hourly values but the horizon is "
            f"{horizon_hours} h (prices.cons length) — add "
            f"{horizon_hours - len(vals)} more"
        )
    vals = vals[:horizon_hours]
    out: list[float] = []
    for v in vals:
        out.extend([v] * STEPS_PER_HOUR)
    return out


def hourly_grid(start: dt.datetime, horizon_hours: int) -> list[dt.datetime]:
    return [start + dt.timedelta(hours=i) for i in range(horizon_hours)]


def interval_grid(start: dt.datetime, horizon_hours: int) -> list[dt.datetime]:
    n = horizon_hours * STEPS_PER_HOUR
    return [start + dt.timedelta(minutes=INTERVAL_MIN * i) for i in range(n)]
