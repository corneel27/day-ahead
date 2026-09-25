"""The Python escape hatch for scenario values that cannot be literals.

A scenario JSON may write {"plugin": "<name>", ...kwargs} (or, for
ev.soc_plugin, {"name": "<name>", ...kwargs}; see ev.py) anywhere the
loader allows it. At run time the registered function is called with a
PluginContext and the remaining keys as kwargs.

Three EV helpers are registered here, ported from test_ev_harness_v6.py:
remainder_soc backs into an actual_soc/wished_level pair that leaves a
sub-minimum-duty remainder on top of N full-power intervals, ready_u_zero
pins the ready deadline just before the end of interval u=0, and
day_rollover drives day_ahead.py's short "HH:MM:SS" ready-time parsing
across midnight.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable

_REGISTRY: dict[str, Callable] = {}


def plugin(name: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"plugin {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return register


def get_plugin(name: str) -> Callable:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario plugin {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def registered() -> list[str]:
    return sorted(_REGISTRY)


@dataclass
class PluginContext:
    """What an EV plugin sees: the frozen solve anchor, the model interval
    length, the sanitised (patched) config, and which EV in
    config["electric_vehicle"] it's being evaluated for."""

    start: dt.datetime
    interval_s: int
    config: dict[str, Any]
    ev_index: int


def _predict_ready_rollover(start_dt: dt.datetime, hh_mm_ss: str) -> dt.datetime:
    """Mirrors day_ahead.py's short-format ready-datetime parsing exactly,
    the len(ready_str) <= 9 branch: same-day HH:MM unless it's at or before
    start_dt's own HH:MM, in which case it rolls to tomorrow. Ported
    verbatim from test_ev_harness_v6._predict_ready_rollover."""
    t = dt.datetime.strptime(hh_mm_ss, "%H:%M:%S")
    ready = dt.datetime(start_dt.year, start_dt.month, start_dt.day, t.hour, t.minute)
    if (ready.hour == start_dt.hour and ready.minute < start_dt.minute) or (
        ready.hour < start_dt.hour
    ):
        ready = ready + dt.timedelta(days=1)
    return ready


@plugin("ready_u_zero")
def _ready_u_zero(ctx: PluginContext, buffer_s: int = 45) -> dict:
    """Port of test_ev_harness_v6.ready_u_zero_full_window. There, both
    ends of the window had to be pinned from one real now() snapshot so the
    achievable charging window couldn't shrink depending on real wall-clock
    timing. Here the clock is frozen at the scenario's own start, already a
    grid boundary (vocabulary.parse_start enforces it), so start already is
    the beginning of interval u=0 and no snapshotting is needed. Just place
    ready just before that interval's end."""
    ready_dt = ctx.start + dt.timedelta(seconds=ctx.interval_s - buffer_s)
    return {"ready_dt": ready_dt}


@plugin("day_rollover")
def _day_rollover(ctx: PluginContext, hour: int = 1, minute: int = 0) -> dict:
    """Port of test_ev_harness_v6.day_rollover_ready_time. The scenario
    JSON supplies its own late-clock start (for example 23:15); this
    computes the short "HH:MM:SS" override string and the predicted
    resolved datetime, so the case-level echo check has something to
    compare against."""
    ready_str = f"{hour:02d}:{minute:02d}:00"
    predicted = _predict_ready_rollover(ctx.start, ready_str)
    return {"ready_dt": predicted, "ready_override_str": ready_str}


@plugin("remainder_soc")
def _remainder_soc(
    ctx: PluginContext,
    full_intervals: int,
    remainder_kwh: float,
    base_soc: float = 30.0,
) -> dict:
    """Port of test_ev_harness_v6.remainder_soc_factory. Backs into an
    (actual_soc, wished_level) pair whose energy need is exactly
    full_intervals whole intervals at the EV's own top-stage power, plus a
    tiny remainder_kwh, engineered to force a sub-minimum-duty sliver
    rather than landing on it by luck. Reads the EV's real capacity,
    charge_stages, and charge_three_phase from ctx.config, so the corpus
    stays correct if that config ever changes."""
    from . import ev as ev_mod

    cfg_ev = ctx.config["electric_vehicle"][ctx.ev_index]
    capacity = float(cfg_ev["capacity"])
    interval_h = ctx.interval_s / 3600
    per_interval = ev_mod.top_stage_accu_kw(ctx.config, ctx.ev_index) * interval_h
    e_needed = full_intervals * per_interval + remainder_kwh
    wished = base_soc + (e_needed / capacity) * 100
    if wished > 100.0:
        raise ValueError(
            f"remainder_soc: full_intervals={full_intervals} needs "
            f"{e_needed:.3f} kWh, which exceeds {cfg_ev.get('name', '?')}'s "
            f"capacity from {base_soc}% — lower full_intervals or base_soc."
        )
    return {"actual_soc": round(base_soc, 4), "wished_level": round(wished, 4)}
