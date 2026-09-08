"""Assertions run against a solved scenario.

S1 ships the **Tier A structural invariants** only — properties that hold
for *any* optimal solution, so they survive solver-version and CPU changes
and tie-breaking. They read the model through ``ModelView`` (the variable
registry), never through log text. Hard fail.

The per-scenario ``expect`` vocabulary (``scheduled``, ``battery_charges_during``,
…) and Tier B/C arrive in S2. Salvaged and trimmed from the untracked
``test_scenarios.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    (arch doc §8.4); Tier C counts it instead (S2)."""

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
