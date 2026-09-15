"""Turn a ``Scenario`` into the dict ``da_debug.ReplayIO`` replays.

``ReplayIO`` serves ``price_data`` / ``prog_data`` / ``baseload`` /
``ha_states`` / ``config`` / ``ha_context`` straight from this dict and
patches away every DB / HA / network call, so nothing here needs a capture.

Everything the scenario expresses hourly is expanded to the 15-minute model
grid. ``price_data`` and ``prog_data`` are built on the *same* grid and the
same length because ``day_ahead.py`` copies price columns onto ``prog_data``
positionally (``day_ahead.py:202``).
"""

from __future__ import annotations

from . import _env  # noqa: F401  -- pins TZ=UTC (g.timestamp() below is tz-sensitive)

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import BASE_STATES_PATH
from .base_config import base_config
from .loader import set_dotted
from .model import Scenario
from .vocabulary import INTERVAL_S, STEPS_PER_HOUR, interval_grid, parse_start, upsample

# A fixed NL location so solar geometry (used by the DAO predictor when a
# scenario *doesn't* inject a solar array) is realistic. de Bilt-ish.
# time_zone is UTC to match the pinned process TZ (see _env.py) — S1 injects
# solar directly so geometry/tz don't bite yet; revisit when a heat-pump /
# solar-geometry scenario needs local solar noon (S5+).
HA_CONTEXT = {
    "latitude": 52.10,
    "longitude": 5.18,
    "time_zone": "UTC",
    "country": "NL",
}

DEFAULT_BASELOAD_KW = 0.25
DEFAULT_TEMP_C = 6.0


def load_base_states() -> dict[str, str]:
    return json.loads(Path(BASE_STATES_PATH).read_text())


def build_config(scenario: Scenario) -> dict:
    cfg = base_config(scenario.options or "options_example")
    for path, value in scenario.config_patch.items():
        set_dotted(cfg, path, value)
    return cfg


def resolve_ev(scenario: Scenario, config: dict):
    """If the scenario has an ``ev`` block, expand it against
    ``config`` — mutating ``config`` in place for ``ev.remove_stop_entity``
    — and return the ``ev.ExpandedEv`` (``None`` otherwise). Called once by
    the runner, before ``build_snapshot``, so both the synthetic states and
    the post-solve case checks (echo verification, capacity sanity) share
    the same resolved input."""
    if scenario.ev is None:
        return None
    from . import ev as ev_mod

    start = parse_start(scenario.start)
    expanded = ev_mod.expand_ev_block(scenario.ev, config=config, start=start, interval_s=INTERVAL_S)
    for path, value in expanded.config_patch.items():
        set_dotted(config, path, value)
    return expanded


def _price_frame(pd, grid: list[dt.datetime], cons_q: list[float], prod_q: list[float]):
    df = pd.DataFrame({
        "time": grid,
        "da_ex": cons_q,
        "da_cons": cons_q,
        "da_prod": prod_q,
        "datasoort": ["expected"] * len(grid),
    })
    df.index = pd.to_datetime(df["time"])
    df.index.name = "time"
    return df


def _prog_frame(pd, grid: list[dt.datetime], temp_q: list[float]):
    df = pd.DataFrame({
        "time": [int(g.timestamp()) for g in grid],
        "tijd": grid,
        "temp": temp_q,
        "glob_rad": [0.0] * len(grid),
    })
    df.index = pd.to_datetime(df["tijd"])
    df.index.name = "tijd"
    return df


def build_snapshot(scenario: Scenario, *, config: dict | None = None, ev_states: dict | None = None) -> dict:
    import pandas as pd

    from dao.prog import da_debug

    start = parse_start(scenario.start)
    horizon_h = scenario.horizon_hours
    grid = interval_grid(start, horizon_h)

    cons_q = upsample(scenario.prices_cons, horizon_h, label="prices.cons")
    prod_src = scenario.prices_prod if scenario.prices_prod is not None else scenario.prices_cons
    prod_q = upsample(prod_src, horizon_h, label="prices.prod")

    temp_src = scenario.temp if scenario.temp is not None else [DEFAULT_TEMP_C] * horizon_h
    temp_q = upsample(temp_src, horizon_h, label="temp")

    if scenario.baseload is not None:
        baseload_hourly = list(scenario.baseload)[:horizon_h]
        if len(baseload_hourly) < 24:
            baseload_hourly += [baseload_hourly[-1]] * (24 - len(baseload_hourly))
    else:
        baseload_hourly = [DEFAULT_BASELOAD_KW] * max(24, horizon_h)

    cfg = config if config is not None else build_config(scenario)

    states = load_base_states()
    for eid, value in scenario.states.items():
        states[eid] = _statestr(value)
    if ev_states:
        for eid, value in ev_states.items():
            states[eid] = _statestr(value)

    price_df = _price_frame(pd, grid, cons_q, prod_q)
    prog_df = _prog_frame(pd, grid, temp_q)

    return {
        "meta": {
            "schema_version": getattr(da_debug, "SCHEMA_VERSION", 1),
            "schema_min_supported": getattr(da_debug, "SCHEMA_MIN_SUPPORTED", 1),
            "captured_at": start.isoformat(),
            "interval": "15min",
            "solver_threads": 1,
            "strategy": "minimize cost",
            "dao_version": da_debug._dao_version(),
            "config_hash": da_debug._config_hash(cfg),
            "scenario_id": scenario.id,
        },
        "ha_context": dict(HA_CONTEXT),
        "price_data": da_debug._dataframe_to_payload(price_df),
        "price_data_args": None,
        "prog_data": da_debug._dataframe_to_payload(prog_df),
        "ha_states": states,
        "baseload": {str(d): list(baseload_hourly) for d in range(7)},
        "heatpump_run_hours": _heatpump_hours_channel(scenario),
        "solar_predictions": {},
        "config": cfg,
    }


def solar_quarter_series(scenario: Scenario) -> list[float]:
    """The scenario's total-house PV in kW on the 15-minute grid (all zero
    when the scenario gives no ``solar`` array). ``runner.py`` splits this
    across the configured PV arrays by capacity share."""
    horizon_h = scenario.horizon_hours
    if scenario.solar is None:
        return [0.0] * (horizon_h * STEPS_PER_HOUR)
    return upsample(scenario.solar, horizon_h, label="solar")


def _heatpump_hours_channel(scenario: Scenario) -> dict:
    # get_heatpump_run_hours is keyed by da_debug._call_key(args, kwargs);
    # day_ahead calls it positionally. An empty dict makes ReplayIO raise a
    # SnapshotMiss naming the exact key it wanted — but options_example's
    # heat pump path does not reach it in the S1 base scenario, so {} is
    # fine until a heat-pump scenario needs it (S5). When heatpump_hours is
    # set we still cannot know the key ahead of time; store it under the
    # value 0-arg key and the 1-arg (entity) key is filled lazily on miss.
    if not scenario.heatpump_hours:
        return {}
    from dao.prog.da_debug import _call_key

    return {_call_key((), {}): float(scenario.heatpump_hours)}


def _statestr(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)
