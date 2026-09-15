"""EV scenario sugar: the ``ev`` JSON block -> ``states`` +
``config_patch`` a solve can run against, plus enough resolved detail for
the post-solve case checks (echo verification, capacity sanity) in
``expectations.py``.

Absorbed from ``test_ev_harness_v6.py``'s ``build_overrides``/``_resolve``/
``_top_stage_accu_kw``, adapted to read the *sanitised config dict*
(``base_config.py``'s output) instead of a live ``DaCalc.ev_options``
object — the whole point of the synthetic-snapshot architecture is that
nothing here touches a real ``DaCalc``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Optional

from . import plugins
from .plugins import PluginContext
from .vocabulary import VocabularyError, parse_offset


def find_ev_index(config: dict, target: str) -> int:
    """The index into ``config["electric_vehicle"]`` whose name contains
    ``target`` (case-insensitive) — mirrors
    ``test_ev_harness_v6._find_ev_index``."""
    for i, ev in enumerate(config.get("electric_vehicle", []) or []):
        if target.lower() in str(ev.get("name", "")).lower():
            return i
    raise KeyError(f"no EV in this config matches target {target!r}")

def _three_phase(cfg_ev: dict) -> bool:
    raw = cfg_ev.get("charge_three_phase")
    val = raw.get("value") if isinstance(raw, dict) else raw
    if isinstance(val, str):
        return val.strip().lower() in ("true", "on", "1", "yes")
    return bool(val)


def top_stage_accu_kw(config: dict, ev_index: int) -> float:
    """Accu-side kW of the EV's highest charge stage — mirrors
    day_ahead.py's own derivation (ampere x phases x 230 / 1000 x
    efficiency), read from the sanitised config instead of a live
    ``FlexBool.resolve()`` call (no HA/entity resolution happens here;
    ``charge_three_phase`` is always a literal in this corpus)."""
    cfg_ev = config["electric_vehicle"][ev_index]
    stages = cfg_ev["charge_stages"]
    top = stages[-1]
    ampere = float(top.get("ampere", 0.0))
    efficiency = float(top.get("efficiency", 1.0) or 1.0)
    phases = 3 if _three_phase(cfg_ev) else 1
    return ampere * phases * 230 / 1000 * efficiency


@dataclass
class ResolvedEvInput:
    """Same shape as the scenario JSON's per-car ``ev``/``ev.other`` block,
    but with ``ready`` fully resolved to a concrete datetime (and/or a raw
    override string) — reused both to build HA-state overrides and to
    verify the solve's own setup echo against what was actually asked for."""

    plugged_in: Optional[bool] = None
    position: Optional[str] = None
    actual_soc: Optional[float] = None
    instant_charge: Optional[bool] = None
    wished_level: Optional[float] = None
    ready_dt: Optional[dt.datetime] = None
    ready_override_str: Optional[str] = None


def _resolve_ready(spec: Any, *, ctx: PluginContext) -> tuple[Optional[dt.datetime], Optional[str]]:
    if spec is None:
        return None, None
    if isinstance(spec, str):
        return parse_offset(spec, ctx.start), None
    if isinstance(spec, dict):
        name = spec.get("plugin")
        if not name:
            raise VocabularyError(f"ev ready plugin object is missing 'plugin': {spec!r}")
        kwargs = {k: v for k, v in spec.items() if k != "plugin"}
        result = plugins.get_plugin(name)(ctx, **kwargs)
        return result.get("ready_dt"), result.get("ready_override_str")
    raise VocabularyError(f"ev ready must be a string offset or a plugin object, got {spec!r}")


def _resolve_input(car: dict, *, ctx: PluginContext) -> ResolvedEvInput:
    ready_dt, ready_override_str = _resolve_ready(car.get("ready"), ctx=ctx)
    return ResolvedEvInput(
        plugged_in=car.get("plugged_in"),
        position=car.get("position"),
        actual_soc=car.get("actual_soc"),
        instant_charge=car.get("instant_charge"),
        wished_level=car.get("wished_level"),
        ready_dt=ready_dt,
        ready_override_str=ready_override_str,
    )


def build_overrides(config: dict, ev_index: int, resolved: ResolvedEvInput) -> dict:
    """Port of ``test_ev_harness_v6.build_overrides``: the resolved input ->
    ``entity_id -> HA-state-string`` overrides, reading entity ids from the
    sanitised config. An unconfigured entity (e.g. ``entity_instant_start``
    is ``None`` for the Golf) is silently skipped here, same as the
    original — that's what the SETUP_MISMATCH / reads check downstream is
    for (case 5.1's shape)."""
    cfg_ev = config["electric_vehicle"][ev_index]
    overrides: dict[str, Any] = {}
    # day_ahead.py unconditionally reads a couple of EV entities purely for
    # logging/deciding whether to toggle/adjust them (all real writes are
    # gated by debug=True under ReplayIO, so these never affect the
    # optimisation) — but an unconditional read still needs a value in
    # `ha_states`. base_states.json already covers the Golf's; a second EV
    # (e.g. Tesla, options_2ev) has no such default, so every EV gets one
    # here.
    if cfg_ev.get("charge_switch"):
        overrides[cfg_ev["charge_switch"]] = "off"
    if cfg_ev.get("entity_set_charging_ampere"):
        overrides[cfg_ev["entity_set_charging_ampere"]] = "16"
    if resolved.plugged_in is not None:
        overrides[cfg_ev["entity_plugged_in"]] = "on" if resolved.plugged_in else "off"
    if resolved.position is not None:
        overrides[cfg_ev["entity_position"]] = resolved.position
    if resolved.actual_soc is not None:
        overrides[cfg_ev["entity_actual_level"]] = resolved.actual_soc
    if resolved.instant_charge is not None and cfg_ev.get("entity_instant_start") is not None:
        overrides[cfg_ev["entity_instant_start"]] = "on" if resolved.instant_charge else "off"
    if resolved.wished_level is not None:
        if resolved.instant_charge and cfg_ev.get("entity_instant_level") is not None:
            overrides[cfg_ev["entity_instant_level"]] = resolved.wished_level
        elif cfg_ev.get("charge_scheduler") is not None:
            overrides[cfg_ev["charge_scheduler"]["entity_set_level"]] = resolved.wished_level
    sched = cfg_ev.get("charge_scheduler")
    if resolved.ready_override_str is not None and sched is not None:
        overrides[sched["entity_ready_datetime"]] = resolved.ready_override_str
    elif resolved.ready_dt is not None and sched is not None:
        overrides[sched["entity_ready_datetime"]] = resolved.ready_dt.strftime("%Y-%m-%d %H:%M:%S")
    return overrides


@dataclass
class ExpandedEv:
    states: dict[str, Any]
    config_patch: dict[str, Any]
    target_index: int
    target_name: str
    target_capacity_kwh: float
    resolved_target: ResolvedEvInput
    other_index: Optional[int] = None
    other_name: Optional[str] = None
    other_capacity_kwh: Optional[float] = None
    resolved_other: Optional[ResolvedEvInput] = None


def expand_ev_block(ev_block: dict, *, config: dict, start: dt.datetime, interval_s: int) -> ExpandedEv:
    """The scenario's ``ev`` block -> HA-state overrides + config patch for
    both the target car and (if present) ``ev.other``. Called once per
    scenario, on the already ``scenario.config_patch``-applied config, so
    ``ev.remove_stop_entity`` composes with any other config_patch."""
    target = ev_block["target"]
    target_index = find_ev_index(config, target)
    target_name = config["electric_vehicle"][target_index]["name"]
    target_capacity = float(config["electric_vehicle"][target_index]["capacity"])
    ctx = PluginContext(start=start, interval_s=interval_s, config=config, ev_index=target_index)

    car = dict(ev_block)
    soc_plugin = ev_block.get("soc_plugin")
    if soc_plugin is not None:
        kwargs = {k: v for k, v in soc_plugin.items() if k != "name"}
        res = plugins.get_plugin(soc_plugin["name"])(ctx, **kwargs)
        car["actual_soc"] = res["actual_soc"]
        car["wished_level"] = res["wished_level"]

    resolved_target = _resolve_input(car, ctx=ctx)
    states = build_overrides(config, target_index, resolved_target)

    config_patch: dict[str, Any] = {}
    if ev_block.get("remove_stop_entity"):
        config_patch[f"electric_vehicle[{target_index}].entity_stop_charging"] = None

    other_index = other_name = other_capacity = resolved_other = None
    other_block = ev_block.get("other")
    if other_block is not None:
        candidates = [i for i in range(len(config["electric_vehicle"])) if i != target_index]
        if len(candidates) != 1:
            raise VocabularyError(
                f"ev.other needs exactly one other EV configured, found {len(candidates)} "
                f"(use \"options\": \"options_2ev\")"
            )
        other_index = candidates[0]
        other_name = config["electric_vehicle"][other_index]["name"]
        other_capacity = float(config["electric_vehicle"][other_index]["capacity"])
        other_ctx = PluginContext(start=start, interval_s=interval_s, config=config, ev_index=other_index)
        resolved_other = _resolve_input(other_block, ctx=other_ctx)
        states.update(build_overrides(config, other_index, resolved_other))

    return ExpandedEv(
        states=states, config_patch=config_patch,
        target_index=target_index, target_name=target_name, target_capacity_kwh=target_capacity,
        resolved_target=resolved_target,
        other_index=other_index, other_name=other_name, other_capacity_kwh=other_capacity,
        resolved_other=resolved_other,
    )
