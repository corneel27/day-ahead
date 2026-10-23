"""Turn a Scenario into the dict da_debug.ReplayIO replays.

ReplayIO serves price_data, prog_data, baseload, ha_states, config, and
ha_context straight from this dict and patches away every DB, HA, and
network call, so nothing here needs a capture.

Everything the scenario expresses hourly is expanded to the model grid
(vocabulary.model_grid): 15-minute intervals for the fixed part, hourly
intervals for the predicted part (prices.predicted). price_data and
prog_data are built on the same grid and the same length, because
day_ahead.py copies price columns onto prog_data positionally.

With a predicted part, day_ahead.py calls get_price_data and
get_prognose_data twice each: once for the fixed part, once for the
predicted part. The snapshot records both calls, in that order, as
da_debug's call-sequence channels expect.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import (
    BASE_STATES_PATH,
    _env,  # noqa: F401  -- pins TZ=UTC (g.timestamp() below is tz-sensitive)
)
from .base_config import base_config
from .loader import set_dotted
from .model import Scenario
from .vocabulary import (
    INTERVAL_S,
    expand_to_model_grid,
    hourly_grid,
    interval_grid,
    model_grid,
    parse_start,
    upsample,
)

# A fixed NL location so solar geometry (used by the DAO predictor when a
# scenario doesn't inject a solar array) is realistic. De Bilt-ish.
# time_zone is UTC to match the pinned process TZ (see _env.py). Every
# scenario today injects solar directly, so geometry and local solar noon
# don't matter yet; revisit if a scenario ever needs to exercise the real
# geometry instead.
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
    if scenario.predicted_hours:
        set_dotted(cfg, "prices.prediction.extension", scenario.predicted_hours)
    for path, value in scenario.config_patch.items():
        set_dotted(cfg, path, value)
    return cfg


def resolve_ev(scenario: Scenario, config: dict):
    """If the scenario has an ev block, expand it against config, mutating
    config in place for ev.remove_stop_entity, and return the
    ev.ExpandedEv (None otherwise). Called once by the runner, before
    build_snapshot, so both the synthetic states and the post-solve case
    checks (echo verification, capacity sanity) share the same resolved
    input."""
    if scenario.ev is None:
        return None
    from . import ev as ev_mod

    start = parse_start(scenario.start)
    expanded = ev_mod.expand_ev_block(scenario.ev, config=config, start=start, interval_s=INTERVAL_S)
    for path, value in expanded.config_patch.items():
        set_dotted(config, path, value)
    return expanded


def _price_frame(pd, grid: list[dt.datetime], cons_q: list[float], prod_q: list[float], datasoort: str = "expected"):
    df = pd.DataFrame({
        "time": grid,
        "da_ex": cons_q,
        "da_cons": cons_q,
        "da_prod": prod_q,
        "datasoort": [datasoort] * len(grid),
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
    fixed_h, pred_h = scenario.fixed_hours, scenario.predicted_hours
    horizon_h = scenario.horizon_hours
    grid = interval_grid(start, fixed_h)
    pred_start = start + dt.timedelta(hours=fixed_h)
    pred_grid = hourly_grid(pred_start, pred_h)

    cons_q = upsample(scenario.prices_cons, fixed_h, label="prices.cons")
    prod_src = scenario.prices_prod if scenario.prices_prod is not None else scenario.prices_cons
    prod_q = upsample(prod_src, fixed_h, label="prices.prod")
    pred_cons = list(scenario.prices_pred_cons)
    pred_prod = list(scenario.prices_pred_prod) if scenario.prices_pred_prod is not None else pred_cons

    temp_src = scenario.temp if scenario.temp is not None else [DEFAULT_TEMP_C] * horizon_h
    temp_all = expand_to_model_grid(temp_src, fixed_h, pred_h, label="temp")
    temp_q, temp_pred = temp_all[: len(grid)], temp_all[len(grid):]

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

    price_calls = [da_debug._sequence_record(
        {"start": start, "end": None, "interval": "15min", "extension": 0},
        _price_frame(pd, grid, cons_q, prod_q),
    )]
    prog_calls = [da_debug._sequence_record(
        {"start": start, "end": pred_start if pred_h else None, "interval": "15min"},
        _prog_frame(pd, grid, temp_q),
    )]
    if pred_h:
        price_calls.append(da_debug._sequence_record(
            {"start": pred_start, "end": None, "interval": "1hour", "extension": pred_h},
            _price_frame(pd, pred_grid, pred_cons, pred_prod, datasoort="prediction"),
        ))
        prog_calls.append(da_debug._sequence_record(
            {"start": pred_start, "end": None, "interval": "1hour"},
            _prog_frame(pd, pred_grid, temp_pred),
        ))

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
        "price_data_calls": price_calls,
        "prog_data_calls": prog_calls,
        "ha_states": states,
        "baseload": {str(d): list(baseload_hourly) for d in range(7)},
        "heatpump_run_hours": _heatpump_hours_channel(scenario),
        "avg_temperature": _avg_temperature_channel(scenario),
        "solar_prediction_calls": {},
        "config": cfg,
    }


def solar_quarter_series(scenario: Scenario) -> list[float]:
    """The scenario's total-house PV in kW on the model grid
    (vocabulary.model_grid), all zero when the scenario gives no solar
    array. runner.py splits this across the configured PV arrays by
    capacity share."""
    n = len(model_grid(parse_start(scenario.start), scenario.fixed_hours, scenario.predicted_hours))
    if scenario.solar is None:
        return [0.0] * n
    return expand_to_model_grid(scenario.solar, scenario.fixed_hours, scenario.predicted_hours, label="solar")


def _heatpump_hours_channel(scenario: Scenario) -> dict:
    # get_heatpump_run_hours is keyed by da_debug._call_key(args, kwargs);
    # day_ahead calls it positionally. An empty dict makes ReplayIO raise a
    # SnapshotMiss naming the exact key it wanted, but options_example's
    # heat pump path never reaches it: entity_heat_produced isn't
    # configured, so day_ahead.py short-circuits first. {} stays correct
    # until a scenario configures that entity. When heatpump_hours is set
    # we still cannot know the key ahead of time, so store it under the
    # 0-arg key; the 1-arg (entity) key gets filled lazily on miss.
    if not scenario.heatpump_hours:
        return {}
    from dao.prog.da_debug import _call_key

    return {_call_key((), {}): float(scenario.heatpump_hours)}


def _avg_temperature_channel(scenario: Scenario) -> dict:
    """Feeds Meteo.get_avg_temperature(), called by day_ahead.py's heating
    block through calc_graaddagen() once the heat pump is enabled: once
    for "today" and, on a horizon longer than a day, again for "tomorrow".
    Both calls pass an already-resolved midnight datetime, never None.
    calc_graaddagen resolves its own date=None default to
    datetime.combine(datetime.today(), time.min) before calling
    get_avg_temperature(date), so the call key here must match that
    resolved value, not the unresolved default. Found by an actual replay:
    the first cut of this used None, and every heat-pump scenario raised a
    clean SnapshotMiss naming the real FakeDatetime(...) key it wanted
    instead.

    A synthetic scenario has no live database to answer that query from,
    so this feeds it the mean of the scenario's own temp array instead,
    the same value prog_data.temp carries. See da_debug.RecordingIO's
    matching capture-side wrap (_wrapped_avg_temperature) for how a real
    installation's capture populates this same channel."""
    from dao.prog.da_debug import _call_key

    hourly = scenario.temp if scenario.temp is not None else [DEFAULT_TEMP_C] * scenario.horizon_hours
    avg_temp = sum(hourly) / len(hourly)
    start = parse_start(scenario.start)
    today_midnight = dt.datetime.combine(start.date(), dt.time())
    channel = {_call_key((today_midnight,), {}): avg_temp}
    if scenario.horizon_hours > 24:
        tomorrow_midnight = dt.datetime.combine(start.date() + dt.timedelta(days=1), dt.time())
        channel[_call_key((tomorrow_midnight,), {})] = avg_temp
    return channel


def _statestr(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)
