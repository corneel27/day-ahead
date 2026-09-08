"""Run one scenario: synthetic snapshot -> hermetic solve -> Tier A.

S1 scope. The per-scenario ``expect`` checks, Tier B baselines and Tier C
metrics land in S2.
"""

from __future__ import annotations

from . import _env  # noqa: F401  -- pins TZ=UTC before day_ahead is imported

import io
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .build_snapshot import build_config, build_snapshot, solar_quarter_series
from .expectations import CheckResult, ResultContext, run_tier_a
from .model import Scenario
from .vocabulary import interval_grid, parse_start

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INFEASIBLE = "INFEASIBLE"
STATUS_ERROR = "ERROR"
STATUS_SKIP = "SKIP"


@dataclass
class ScenarioResult:
    id: str
    description: str
    status: str
    objective: float | None = None
    checks: list[CheckResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_PASS, STATUS_SKIP)


def _capacity_of(solar_option) -> float:
    strings = getattr(solar_option, "strings", None) or []
    if strings:
        return float(sum(getattr(s, "capacity", 0.0) or 0.0 for s in strings))
    return float(getattr(solar_option, "capacity", 0.0) or 0.0)


def _solar_patch(scenario: Scenario):
    """Return a replacement ``DaBase.calc_solar_predictions`` that serves the
    scenario's own PV series, split across the configured arrays by
    installed capacity. Layered on top of ReplayIO's patches by the runner.
    """
    import pandas as pd

    start = parse_start(scenario.start)
    grid = interval_grid(start, scenario.horizon_hours)
    total_kw = solar_quarter_series(scenario)  # len == horizon*4, on `grid`

    def calc_solar_predictions(self, solar_option, vanaf, tot, interval=None, _ml_prediction=None):
        caps = []
        for so in list(getattr(self, "solar", []) or []):
            caps.append(_capacity_of(so))
        for b in getattr(self, "battery_options", []) or []:
            for so in getattr(b, "solar", []) or []:
                caps.append(_capacity_of(so))
        total_cap = sum(caps) or 1.0
        share = _capacity_of(solar_option) / total_cap

        rows_tijd, rows_pred = [], []
        for t, kw in zip(grid, total_kw):
            if t < vanaf or t >= tot:
                continue
            rows_tijd.append(t)
            rows_pred.append(round(kw * share, 6))
        return pd.DataFrame({"tijd": rows_tijd, "prediction": rows_pred})

    return calc_solar_predictions


def _capture_root_log():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    prev_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    def stop() -> str:
        root.removeHandler(handler)
        root.setLevel(prev_level)
        return buf.getvalue()

    return stop


def run_scenario(scenario: Scenario) -> ScenarioResult:
    if scenario.skip:
        return ScenarioResult(scenario.id, scenario.description, STATUS_SKIP,
                              failures=[scenario.skip_reason or "skip: true"])

    from dao.prog import da_debug

    try:
        config = build_config(scenario)
        snapshot = build_snapshot(scenario, config=config)
        solar_quarter_series(scenario)  # validate the solar array length up front
    except Exception as ex:  # noqa: BLE001 - reported, not swallowed
        return ScenarioResult(scenario.id, scenario.description, STATUS_ERROR,
                              failures=[f"snapshot build failed: {ex}"])

    start = parse_start(scenario.start)
    stop_log = _capture_root_log()
    model = registry = None
    num_solutions = 0
    exc: BaseException | None = None
    try:
        da_debug._ensure_day_ahead_importable()
        from day_ahead import DaCalc

        tmp_opts = Path(tempfile.mkdtemp(prefix="dao-scenario-")) / "options.json"
        tmp_opts.write_text("{}")

        with da_debug.ReplayIO(snapshot, solver_threads=1) as replay:
            from dao.prog.da_base import DaBase

            replay._patches.set(
                DaBase, "calc_solar_predictions", _solar_patch(scenario)
            )
            dacalc = DaCalc(str(tmp_opts))
            dacalc._debug_capture_vars = True
            try:
                dacalc.calc_optimum(_start_dt=start)
            except da_debug.SnapshotMiss as miss:
                log_text = stop_log()
                return ScenarioResult(
                    scenario.id, scenario.description, STATUS_ERROR,
                    failures=[f"replay hit a gap in the synthetic snapshot: {miss}"],
                )
            model = replay._model
            registry = getattr(dacalc, "_debug_vars", None)
            num_solutions = model.num_solutions if model is not None else 0
    except BaseException as ex:  # noqa: BLE001
        exc = ex
    finally:
        log_text = stop_log()

    if exc is not None:
        return ScenarioResult(
            scenario.id, scenario.description, STATUS_ERROR,
            failures=[f"solve raised {type(exc).__name__}: {exc}"],
        )

    objective = None
    if model is not None and num_solutions > 0:
        objective = model.objective_value

    rc = ResultContext(model=model, registry=registry, log_text=log_text,
                       num_solutions=num_solutions)
    checks = run_tier_a(rc)

    solved = next(c for c in checks if c.name == "solved")
    if not solved.ok:
        return ScenarioResult(scenario.id, scenario.description, STATUS_INFEASIBLE,
                              objective=objective, checks=checks,
                              failures=[f"[Tier A] solved: {solved.detail}"])

    failures = [f"[Tier A] {c.name}: {c.detail}" for c in checks if not c.ok]
    status = STATUS_PASS if not failures else STATUS_FAIL
    return ScenarioResult(scenario.id, scenario.description, status,
                          objective=objective, checks=checks, failures=failures)
