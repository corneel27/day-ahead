"""The small declarative vocabulary a scenario JSON uses.

Parses the ``start`` anchor and expands the hourly ``prices`` / ``solar`` /
``baseload`` / ``temp`` arrays to the 15-minute model grid. Also provides
two primitives needed by the EV port: a relative time *offset*
(``"+8h"``, ``"+3h20m"``, ``"-24h"``) resolved against ``start``, and a
same-day ``"HH:MM"``-``"HH:MM"`` window resolved to a pair of interval
indices, used by the ``battery_charges_during`` family of case checks.
"""

from __future__ import annotations

import datetime as dt
import re

INTERVAL_MIN = 15
STEPS_PER_HOUR = 60 // INTERVAL_MIN  # 4
INTERVAL_S = INTERVAL_MIN * 60


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


_OFFSET_RE = re.compile(
    r"^(?P<sign>[+-])"
    r"(?:(?P<hours>\d+(?:\.\d+)?)h)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)m)?$"
)


def parse_offset(spec: str, start: dt.datetime) -> dt.datetime:
    """``"+8h"`` / ``"+3h20m"`` / ``"-24h"`` resolved against ``start`` —
    the EV port's ``ready`` shorthand. At least one of ``h``/``m`` must
    be present; sign applies to both."""
    if not isinstance(spec, str):
        raise VocabularyError(f"offset must be a string like '+8h', got {spec!r}")
    m = _OFFSET_RE.match(spec.strip())
    if not m or (m.group("hours") is None and m.group("minutes") is None):
        raise VocabularyError(f"offset {spec!r} is not '[+-]NhNm' (e.g. '+8h', '+3h20m', '-24h')")
    sign = -1 if m.group("sign") == "-" else 1
    hours = float(m.group("hours") or 0)
    minutes = float(m.group("minutes") or 0)
    return start + sign * dt.timedelta(hours=hours, minutes=minutes)


def parse_time_of_day(hhmm: str, *, on_or_after: dt.datetime) -> dt.datetime:
    """``"HH:MM"`` resolved to the first datetime at/after ``on_or_after``
    carrying that time of day — same day if it's still ahead, tomorrow
    otherwise. Used by the ``*_during``/``*_in_window`` case checks,
    whose ``start``/``end`` are clock times, not full datetimes."""
    try:
        t = dt.datetime.strptime(hhmm.strip(), "%H:%M")
    except (ValueError, AttributeError) as ex:
        raise VocabularyError(f"window time {hhmm!r} is not 'HH:MM'") from ex
    candidate = on_or_after.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if candidate < on_or_after:
        candidate += dt.timedelta(days=1)
    return candidate


def window_indices(start: dt.datetime, horizon_hours: int, window_start: str, window_end: str) -> range:
    """The half-open range of interval indices ``u`` covering clock times
    ``[window_start, window_end)`` on the scenario's own grid. ``end`` at or
    before ``start`` rolls to the next day, mirroring ``parse_time_of_day``."""
    w_start = parse_time_of_day(window_start, on_or_after=start)
    w_end = parse_time_of_day(window_end, on_or_after=w_start + dt.timedelta(minutes=INTERVAL_MIN))
    n = horizon_hours * STEPS_PER_HOUR
    u0 = max(0, int((w_start - start).total_seconds() // (INTERVAL_MIN * 60)))
    u1 = min(n, int((w_end - start).total_seconds() // (INTERVAL_MIN * 60)))
    return range(u0, max(u0, u1))
