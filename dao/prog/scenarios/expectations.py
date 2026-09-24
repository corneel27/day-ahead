"""Assertions run against a solved scenario.

The **Tier A structural invariants** are properties that hold for *any*
optimal solution, so they survive solver-version/CPU/tie-breaking changes.
They read the model through ``ModelView`` (the variable registry), never
through log text. Hard fail, always run, never listed in ``expect``.

The **setup checks** are the always-on SETUP_MISMATCH / echo / duty-sliver
checks on a scenario's own overrides. Their own registry (``@setup_check``,
dispatched by ``run_setup_checks`` below) keeps them apart from Tier A and
from the case checks: a failure here says the scenario tests nothing, which
is a different claim from "the model is broken" or "the behaviour is
wrong".

The rest of the ``expect`` vocabulary is handled as **Tier B, case
checks** — one function per ``expect`` key, dispatched by
``run_case_checks`` below. Most read ``ModelView`` too; the EV-specific
ones (``scheduled``, ``reason_contains``, …) read the parsed EV log
instead, since day_ahead.py's scheduling *decision* (and its Dutch reason
string) isn't a model variable. Also here: **Tier C, the objective
baseline** (``objective_within_baseline``) — dispatched through the same
registry as an implementation detail, not a statement about which group it
belongs to.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

SUCCESS_LINE = "Het programma heeft een optimale oplossing gevonden."

# stage_factor is [e][ecs][u] (stage-before-interval), unlike every other
# per-EV container — a transposed read produces plausible wrong numbers.
_DUTY_ZERO_TOL = 1e-4


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


class ResultContext:
    """What the invariants see after a solve."""

    def __init__(self, *, model, registry, log_text: str, num_solutions: int):
        self.model = model
        self.registry = registry
        self.log_text = log_text
        self.num_solutions = num_solutions
        self._mv = None
        if model is not None and registry:
            from .modelview import ModelView

            self._mv = ModelView(model, registry)

    @property
    def mv(self):
        return self._mv


# --- Tier A invariants -----------------------------------------------------


class Invariant:
    name = "invariant"

    def check(self, rc: ResultContext) -> CheckResult:
        raise NotImplementedError

    def _ok(self, detail: str = "") -> CheckResult:
        return CheckResult(self.name, True, detail)

    def _fail(self, detail: str) -> CheckResult:
        return CheckResult(self.name, False, detail)


class Solved(Invariant):
    """Fail-closed: the exact Dutch success line was logged *and* the model
    carries a solution. Not "no failure seen" — a fully infeasible solve
    returns ``None`` before any dispatch logging."""

    name = "solved"

    def check(self, rc):
        has_line = SUCCESS_LINE in rc.log_text
        has_sol = rc.model is not None and rc.num_solutions > 0
        if has_line and has_sol:
            return self._ok()
        bits = []
        if not has_sol:
            bits.append("model has no solution")
        if not has_line:
            bits.append(f"{SUCCESS_LINE!r} not in log")
        return self._fail("; ".join(bits))


class NoSimultaneousChargeDischarge(Invariant):
    """No interval charges and discharges the same battery on the AC side.
    The DC-side ``dc_to_bat``/``dc_from_bat`` pair is deliberately not
    checked — it is not exclusivity-constrained in the current formulation
    (arch doc §7); Tier D counts it instead (S2)."""

    name = "no_simultaneous_charge_discharge"

    def check(self, rc):
        mv = rc.mv
        if mv is None or not (mv.has("ac_to_dc_on") and mv.has("ac_from_dc_on")):
            return self._ok("no AC-coupled battery in this model")
        charge = dict(mv.items("ac_to_dc_on"))
        bad = [
            f"b{b} u{u}"
            for (b, u), disc in mv.items("ac_from_dc_on")
            if disc > 0.5 and charge.get((b, u), 0.0) > 0.5
        ]
        if bad:
            return self._fail(f"battery charging AND discharging at: {', '.join(bad[:8])}")
        return self._ok()


class Sos2Adjacent(Invariant):
    """Every active SOS2 weight pair is a single stage or two adjacent
    stages, on every interval, for every curve (battery charge/discharge +
    heat pump). A non-adjacent pair is a solver-correctness signal and,
    given the mip 1.17.6 SOS2 crash class (arch doc §3), worth watching on
    every case."""

    name = "sos2_adjacent"

    def check(self, rc):
        if rc.mv is None:
            return self._ok("no solved model")
        from dao.prog.da_debug import _sos2_reports

        failures = []
        for u in range(rc.mv.max_u + 1):
            for report in _sos2_reports(
                rc.model, rc.registry.by_idx, rc.registry.samples, u
            ):
                if report["case"] == "error" or not report["adjacent"]:
                    failures.append(
                        f"{report['curve']} asset {report['asset']} u{u}: "
                        f"non-adjacent weights {report['weights']}"
                    )
        if failures:
            return self._fail("; ".join(failures[:6]))
        return self._ok()


class VarBoundsRespected(Invariant):
    """Every variable sits within its own declared ``[lb, ub]``. CBC
    guarantees this for a returned solution; checking it catches
    serialization corruption and feasibility-tolerance blow-ups that would
    otherwise surface only as a weird dispatch."""

    name = "var_bounds_respected"

    def check(self, rc):
        if rc.model is None:
            return self._ok("no model")
        from dao.prog.da_debug import label_for_var

        tol = 1e-6
        bad = []
        for v in rc.model.vars:
            x = v.x
            if x is None:
                continue
            if x < v.lb - tol or x > v.ub + tol:
                bad.append(
                    f"{label_for_var(v, rc.registry.by_idx)}={x:.4f} not in [{v.lb},{v.ub}]"
                )
            if len(bad) >= 6:
                break
        if bad:
            return self._fail("; ".join(bad))
        return self._ok()


class SocWithinLimits(Invariant):
    """State of charge stays within each battery's ``soc`` variable bounds
    across the whole horizon — needs no config parsing, holds for any
    optimal solution."""

    name = "soc_within_limits"

    def check(self, rc):
        mv = rc.mv
        if mv is None or not mv.has("soc"):
            return self._ok("no battery SoC in this model")
        tol = 1e-4
        bad = []
        for (b, u), soc in mv.items("soc"):
            var = mv.var("soc", b, u)
            if soc < var.lb - tol or soc > var.ub + tol:
                bad.append(f"soc[b{b}][{u}]={soc:.3f} not in [{var.lb},{var.ub}]")
        if bad:
            return self._fail("; ".join(bad[:6]))
        return self._ok()


def _ev_indices(mv) -> list[int]:
    if mv is None or not mv.has("stage_factor"):
        return []
    return sorted({idx[0] for idx in mv.by_container["stage_factor"]})


class EvSingleRealStagePerInterval(Invariant):
    """At most one real charge stage (ecs >= 1) active per interval, per EV
    — multi-stage exclusivity, read from ``stage_factor[e][ecs][u]``."""

    name = "ev_single_real_stage_per_interval"

    def check(self, rc):
        mv = rc.mv
        evs = _ev_indices(mv)
        if not evs:
            return self._ok("no EV in this model")
        failures = []
        for e in evs:
            per_u: dict[int, list[float]] = {}
            for (ee, ecs, u), val in mv.items("stage_factor"):
                if ee == e and ecs >= 1:
                    per_u.setdefault(u, []).append(val)
            hot = [u for u, fs in per_u.items() if sum(1 for f in fs if f > _DUTY_ZERO_TOL) > 1]
            if hot:
                failures.append(f"e{e}: multiple real stages at u={sorted(hot)[:8]}")
        if failures:
            return self._fail("; ".join(failures))
        return self._ok()


class EvChargeNonNegative(Invariant):
    """Every EV charge quantity is >= 0 and no stage factor exceeds 1 — the
    cheap "the EV block isn't producing nonsense" check that needs no
    per-case duty tolerance (that lands with the EV port in S2)."""

    name = "ev_charge_non_negative"

    def check(self, rc):
        mv = rc.mv
        if mv is None or not mv.has("stage_factor"):
            return self._ok("no EV in this model")
        bad = [
            f"stage_factor[{e}][{cs}][{u}]={f:.4f}"
            for (e, cs, u), f in mv.items("stage_factor")
            if f < -1e-6 or f > 1.0 + 1e-6
        ]
        if bad:
            return self._fail("; ".join(bad[:6]))
        return self._ok()


TIER_A_INVARIANTS: list[Invariant] = [
    Solved(),
    NoSimultaneousChargeDischarge(),
    Sos2Adjacent(),
    VarBoundsRespected(),
    SocWithinLimits(),
    EvSingleRealStagePerInterval(),
    EvChargeNonNegative(),
]


def run_tier_a(rc: ResultContext) -> list[CheckResult]:
    return [inv.check(rc) for inv in TIER_A_INVARIANTS]


# --- Setup checks --------------------------------------------------------

_SETUP_CHECKS: dict[str, Callable[["CaseContext"], Optional[CheckResult] | list[CheckResult]]] = {}


def setup_check(name: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        _SETUP_CHECKS[name] = fn
        return fn

    return register


@setup_check("overrides_were_read")
def _check_overrides_were_read(ctx: "CaseContext") -> Optional[CheckResult]:
    """Runs when the scenario's ``states`` (literal or EV-derived) is not
    empty: fails if an override names an entity the solve never read via
    ``get_state`` — the SETUP_MISMATCH class of bug, e.g. an override
    aimed at an entity that's unconfigured for this EV (case 5.1's shape)."""
    names = set(ctx.requested_states)
    if not names:
        return None
    unread = sorted(names - ctx.reads)
    if unread:
        return CheckResult(
            "overrides_were_read", False,
            f"override(s) named an entity the solve never read (SETUP_MISMATCH): {unread}",
        )
    return CheckResult("overrides_were_read", True)


@setup_check("setup_echo_matches")
def _check_setup_echo(ctx: "CaseContext") -> Optional[CheckResult]:
    """Runs when the scenario has an ``ev`` block: diff the log's own setup
    echo against what was requested, plus each car's capacity sanity check
    — both ported from ``test_ev_harness_v6``'s SETUP_MISMATCH path."""
    if ctx.expanded_ev is None or ctx.parsed_target is None:
        return None
    from .parsing import check_capacity, verify_setup_echo

    mismatches = verify_setup_echo(ctx.expanded_ev.resolved_target, ctx.parsed_target.setup_echo)
    note = check_capacity(ctx.expanded_ev.target_capacity_kwh, ctx.parsed_target.setup_echo,
                           label=ctx.expanded_ev.target_name)
    if note:
        mismatches.append(note)
    if ctx.parsed_other is not None and ctx.expanded_ev.other_name:
        note2 = check_capacity(ctx.expanded_ev.other_capacity_kwh, ctx.parsed_other.setup_echo,
                                label=ctx.expanded_ev.other_name)
        if note2:
            mismatches.append(note2)
    if mismatches:
        return CheckResult("setup_echo_matches", False, "; ".join(mismatches))
    return CheckResult("setup_echo_matches", True)


@setup_check("no_duty_slivers")
def _check_duty_slivers(ctx: "CaseContext") -> list[CheckResult]:
    """Runs when the scenario has an ``ev`` block: no real charge stage, on
    either car, runs below the minimum duty cycle — mirrors
    ``test_ev_harness_v6.run_case``'s unconditional per-case sliver check,
    with one correction: when day_ahead.py's own min-duty *feasibility
    guard* fired for that car (``minimale schakelduur ... niet
    toegepast`` — energy_needed is below one switching action, so the
    constraint was never added to the model), a sub-minimum factor is the
    legitimate cheapest dispatch, not a violation of a constraint that
    isn't there. v6's blanket check never had to draw this distinction
    because its own tuning happened not to produce a sliver on the one
    case (7.5) where the guard fires; this config's smaller EV battery
    does produce one, which is what surfaced the gap."""
    out: list[CheckResult] = []
    from .parsing import EV_MIN_DUTY_S, NOMINAL_MIN_DUTY

    for label, parsed in (("target", ctx.parsed_target), ("other", ctx.parsed_other)):
        if parsed is None or not parsed.duty_slivers or parsed.min_duty_guard_fired:
            continue
        detail = ", ".join(f"{uur} stage {k} factor {f:.4f}" for uur, k, f in parsed.duty_slivers)
        out.append(CheckResult(
            f"no_duty_slivers[{label}]", False,
            f"DUTY SLIVER below minimum duty {NOMINAL_MIN_DUTY:.4f} ({EV_MIN_DUTY_S:.0f}s) at: {detail}",
        ))
    return out


def run_setup_checks(ctx: "CaseContext") -> list[CheckResult]:
    """Every registered setup check whose precondition holds, in
    registration order. An author cannot skip one by leaving a key out of
    ``expect`` — they take no ``expect`` key at all."""
    results: list[CheckResult] = []
    for fn in _SETUP_CHECKS.values():
        out = fn(ctx)
        if out is None:
            continue
        if isinstance(out, list):
            results.extend(out)
        else:
            results.append(out)
    return results


# --- Tier B, case checks ---------------------------------------------------


@dataclass
class CaseContext:
    """What a setup check or a case check sees, built once per solved
    scenario by ``runner.run_scenario`` and handed to every setup check and
    every ``expect`` key's handler."""

    mv: Any  # ModelView | None, reused from the Tier A ResultContext
    scenario_id: str
    start: dt.datetime
    horizon_hours: int
    objective: Optional[float]
    max_gap: float
    reads: set[str]
    requested_states: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)
    expanded_ev: Optional[Any] = None  # ev.ExpandedEv
    parsed_target: Optional[Any] = None  # parsing.ParsedEvRun
    parsed_other: Optional[Any] = None  # parsing.ParsedEvRun


_CASE_CHECKS: dict[str, Callable[[Any, CaseContext], CheckResult]] = {}


def case_check(key: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        _CASE_CHECKS[key] = fn
        return fn

    return register


def _ev_check(name: str, got, expected, extra: str = "") -> CheckResult:
    ok = got == expected
    detail = f"expected {expected!r}, got {got!r}" + (f" — {extra}" if extra else "")
    return CheckResult(name, ok, "" if ok else detail)


@case_check("scheduled")
def _check_scheduled(value: bool, ctx: CaseContext) -> CheckResult:
    got = ctx.parsed_target.scheduled if ctx.parsed_target else None
    return _ev_check("scheduled", got, value)


@case_check("other_scheduled")
def _check_other_scheduled(value: bool, ctx: CaseContext) -> CheckResult:
    got = ctx.parsed_other.scheduled if ctx.parsed_other else None
    return _ev_check("other_scheduled", got, value)


@case_check("reason_contains")
def _check_reason_contains(value: str, ctx: CaseContext) -> CheckResult:
    reason = ctx.parsed_target.reason if ctx.parsed_target else None
    ok = bool(reason) and value in reason
    detail = "" if ok else f"expected reason containing {value!r}, got {reason!r}"
    return CheckResult("reason_contains", ok, detail)


@case_check("partial_at_least")
def _check_partial_at_least(value: int, ctx: CaseContext) -> CheckResult:
    got = ctx.parsed_target.partial_stops if ctx.parsed_target else None
    ok = got is not None and got >= value
    detail = "" if ok else (
        f"expected at least {value} partial interval(s), got {got} — this is a "
        f"NEGATIVE test (asserts no duty slivers), so without a partial "
        f"interval it passes while testing nothing"
    )
    return CheckResult("partial_at_least", ok, detail)


@case_check("min_duty_guard")
def _check_min_duty_guard(value: bool, ctx: CaseContext) -> CheckResult:
    got = ctx.parsed_target.min_duty_guard_fired if ctx.parsed_target else None
    return _ev_check("min_duty_guard", got, value)


@case_check("wished_level_clipped")
def _check_wished_level_clipped(value: bool, ctx: CaseContext) -> CheckResult:
    got = ctx.parsed_target.wished_level_clipped if ctx.parsed_target else None
    return _ev_check("wished_level_clipped", got, value)


_INTERVAL_H = 0.25  # the fixed 15-minute model grid every scenario solves on


def _window_range(ctx: CaseContext, params: dict) -> range:
    from .vocabulary import window_indices

    return window_indices(ctx.start, ctx.horizon_hours, params["start"], params["end"])


def _battery_flow_kwh(mv, container: str, window: range) -> float:
    if mv is None or not mv.has(container):
        return 0.0
    return sum(v * _INTERVAL_H for (_b, u), v in mv.items(container) if u in window)


@case_check("battery_charges_during")
def _check_battery_charges_during(value: dict, ctx: CaseContext) -> CheckResult:
    window = _window_range(ctx, value)
    kwh = _battery_flow_kwh(ctx.mv, "dc_to_bat", window)
    ok = kwh >= value["min_kwh"]
    detail = "" if ok else f"{kwh:.3f} kWh charged in {value['start']}-{value['end']}, wanted >= {value['min_kwh']}"
    return CheckResult("battery_charges_during", ok, detail)


@case_check("battery_discharges_during")
def _check_battery_discharges_during(value: dict, ctx: CaseContext) -> CheckResult:
    window = _window_range(ctx, value)
    kwh = _battery_flow_kwh(ctx.mv, "dc_from_bat", window)
    ok = kwh >= value["min_kwh"]
    detail = "" if ok else f"{kwh:.3f} kWh discharged in {value['start']}-{value['end']}, wanted >= {value['min_kwh']}"
    return CheckResult("battery_discharges_during", ok, detail)


@case_check("battery_flat_during")
def _check_battery_flat_during(value: dict, ctx: CaseContext) -> CheckResult:
    window = _window_range(ctx, value)
    kwh = (_battery_flow_kwh(ctx.mv, "dc_to_bat", window)
           + _battery_flow_kwh(ctx.mv, "dc_from_bat", window))
    ok = kwh <= value["max_kwh"]
    detail = "" if ok else f"{kwh:.3f} kWh of battery activity in {value['start']}-{value['end']}, wanted <= {value['max_kwh']}"
    return CheckResult("battery_flat_during", ok, detail)


@case_check("no_cross_battery_charge_discharge")
def _check_no_cross_battery_charge_discharge(value: bool, ctx: CaseContext) -> CheckResult:
    """No interval has one battery charging on the AC side while a
    *different* battery discharges on the AC side. Unlike
    ``NoSimultaneousChargeDischarge`` (Tier A, per-battery, backed by the
    real ``ac_to_dc_on[b][u] + ac_from_dc_on[b][u] <= 1`` MILP constraint),
    nothing in the model forbids this across batteries — round-tripping one
    battery's charge into another's discharge is only ever sub-optimal
    (AC/DC conversion losses, cycle cost), never infeasible. So this is a
    Tier B case check, opt-in per multi-battery scenario, not a structural
    invariant."""
    name = "no_cross_battery_charge_discharge"
    if not value:
        return CheckResult(name, True, "explicitly unchecked")
    mv = ctx.mv
    if mv is None or not (mv.has("ac_to_dc_on") and mv.has("ac_from_dc_on")):
        return CheckResult(name, True, "no AC-coupled battery in this model")
    charging: dict[int, set[int]] = {}
    for (b, u), on in mv.items("ac_to_dc_on"):
        if on > 0.5:
            charging.setdefault(u, set()).add(b)
    discharging: dict[int, set[int]] = {}
    for (b, u), on in mv.items("ac_from_dc_on"):
        if on > 0.5:
            discharging.setdefault(u, set()).add(b)
    bad = [
        f"u{u}: charging b{sorted(charging[u])}, discharging b{sorted(discharging[u])}"
        for u in sorted(charging)
        if u in discharging
    ]
    if bad:
        return CheckResult(name, False, f"cross-battery charge/discharge at: {'; '.join(bad[:6])}")
    return CheckResult(name, True)


@case_check("heatpump_runs")
def _check_heatpump_runs(value: dict, ctx: CaseContext) -> CheckResult:
    window = _window_range(ctx, value)
    mv = ctx.mv
    if mv is None or not mv.has("p_hp"):
        # No heat demand at all (heat_needed <= 0, day_ahead.py:2229) means
        # the model never allocates p_hp — a legitimate "didn't run", not a
        # missing-model error. Only fail this branch when the scenario
        # actually expected it to run.
        ok = not value.get("runs", True)
        return CheckResult("heatpump_runs", ok, "" if ok else "no heat pump in this model")
    watts = sum(v for (_s, u), v in mv.items("p_hp") if u in window)
    ran = watts > 1.0
    expected = bool(value.get("runs", True))
    ok = ran == expected
    detail = "" if ok else f"heat pump power in {value['start']}-{value['end']} sums to {watts:.1f} W, expected runs={expected}"
    return CheckResult("heatpump_runs", ok, detail)


def _resolve_machine_index(spec: Any, config: dict[str, Any]) -> tuple[Optional[int], list[str]]:
    """``spec`` is the scenario's ``expect.machine_runs_in_window.machine`` —
    normally a name matching ``config["machines"][*]["name"]`` (e.g.
    ``"wasmachine"``), case-insensitively; a numeric index is also accepted
    as an escape hatch. Returns ``(index_or_None, configured_names)``."""
    machines = config.get("machines") or []
    names = [str(m.get("name", "")) for m in machines]
    spec_str = str(spec)
    for i, name in enumerate(names):
        if name.lower() == spec_str.lower():
            return i, names
    try:
        idx = int(spec)
    except (TypeError, ValueError):
        return None, names
    return (idx if 0 <= idx < len(machines) else None), names


@case_check("machine_runs_in_window")
def _check_machine_runs_in_window(value: dict, ctx: CaseContext) -> CheckResult:
    window = _window_range(ctx, value)
    mv = ctx.mv
    if mv is None or not mv.has("c_ma_u"):
        return CheckResult("machine_runs_in_window", False, "no machine in this model")
    m_idx, names = _resolve_machine_index(value["machine"], ctx.config)
    if m_idx is None:
        return CheckResult(
            "machine_runs_in_window", False,
            f"unknown machine {value['machine']!r}; configured machines: {names}",
        )
    ran = any(
        v > 1e-6 for (m, u), v in mv.items("c_ma_u") if m == m_idx and u in window
    )
    ok = ran == bool(value.get("runs", True))
    detail = "" if ok else (
        f"machine {value['machine']!r} (index {m_idx}) runs in "
        f"{value['start']}-{value['end']}: {ran}, expected {value.get('runs', True)}"
    )
    return CheckResult("machine_runs_in_window", ok, detail)


@case_check("objective_within_baseline")
def _check_objective_within_baseline(value: bool, ctx: CaseContext) -> CheckResult:
    from . import baseline

    if not value:
        return CheckResult("objective_within_baseline", True, "explicitly unchecked")
    status, detail = baseline.check_tier_c(ctx.scenario_id, ctx.objective, tolerance=ctx.max_gap)
    ok = status != baseline.STATUS_FAIL
    return CheckResult("objective_within_baseline", ok, f"{status}: {detail}")


def run_case_checks(expect: dict[str, Any], ctx: CaseContext) -> list[CheckResult]:
    """Every non-``solved`` key in ``expect``, dispatched by name."""
    results: list[CheckResult] = []
    for key, value in expect.items():
        if key == "solved":
            continue
        handler = _CASE_CHECKS.get(key)
        if handler is None:
            results.append(CheckResult(key, False, f"no case check registered for {key!r}"))
            continue
        results.append(handler(value, ctx))
    return results
