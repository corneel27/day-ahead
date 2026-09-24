"""Run one scenario: synthetic snapshot -> hermetic solve -> Tier A ->
setup checks -> Tier B case checks -> Tier C.

Builds the synthetic snapshot (including ``ev`` block expansion via
``build_snapshot.resolve_ev``), solves it hermetically, runs the Tier A
structural invariants, then the always-on setup checks
(``expectations.run_setup_checks``), then the per-scenario ``expect`` case
checks (``expectations.run_case_checks``) — which also dispatches the
Tier C objective-baseline comparison as one of its ``expect`` keys.
"""

from __future__ import annotations

from . import _env  # noqa: F401  -- pins TZ=UTC before day_ahead is imported

import io
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .build_snapshot import build_config, build_snapshot, resolve_ev, solar_quarter_series
from .expectations import (
    CaseContext,
    CheckResult,
    ResultContext,
    run_case_checks,
    run_setup_checks,
    run_tier_a,
)
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
    setup_checks: list[CheckResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    threads: int = 1
    log_path: str | None = None
    png_path: str | None = None
    # EV reporting detail (None for non-EV scenarios) — populated after Tier
    # A passes, consumed by reporting.write_reports.
    parsed_target: object | None = None
    parsed_other: object | None = None
    stats: object | None = None

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


def _expected_png_path(module_dir: Path, start) -> Path:
    """Where day_ahead.py's unconditional ``plt.savefig(...)`` (L5080-5081)
    lands: a path relative to cwd, which day_ahead.py assumes is its own
    directory (``dao/prog``) — the same assumption ``da_debug``'s own
    capture/replay commands make. ``run_scenario`` chdirs there for the
    duration of the solve when ``keep_png=True`` so this resolves correctly
    regardless of where the caller invoked it from."""
    return (module_dir / ".." / "data" / "images" / f"calc_{start.strftime('%Y-%m-%d__%H-%M')}.png").resolve()


def run_scenario(
    scenario: Scenario,
    *,
    threads: int = 1,
    keep_png: bool = False,
    report_dir: Path | None = None,
) -> ScenarioResult:
    """Solve one scenario hermetically.

    ``threads`` is forwarded to ``ReplayIO`` (mip.Model.threads semantics:
    ``-1`` = all cores). Default ``1`` for reproducibility; pass a different
    value and compare the objective / log against a ``threads=1`` run to see
    whether the two agree.

    ``keep_png=True`` keeps day_ahead.py's dispatch chart (suppressed by
    default) and, if ``report_dir`` is given, moves it to
    ``<report_dir>/<id>.png``. ``report_dir`` also controls where the
    combined Python + CBC log is written when the caller asks for it via
    ``write_log`` on the CLI — see ``da_debug.cmd_scenario_run``.
    """
    if scenario.skip:
        return ScenarioResult(scenario.id, scenario.description, STATUS_SKIP,
                              failures=[scenario.skip_reason or "skip: true"], threads=threads)

    from dao.prog import da_debug

    try:
        config = build_config(scenario)
        expanded_ev = resolve_ev(scenario, config)  # may patch `config` in place (remove_stop_entity)
        snapshot = build_snapshot(scenario, config=config,
                                  ev_states=(expanded_ev.states if expanded_ev else None))
        solar_quarter_series(scenario)  # validate the solar array length up front
    except Exception as ex:  # noqa: BLE001 - reported, not swallowed
        return ScenarioResult(scenario.id, scenario.description, STATUS_ERROR,
                              failures=[f"snapshot build failed: {ex}"], threads=threads)

    max_gap_raw = (config.get("max_gap") or {}).get("value", 0.005)
    try:
        max_gap = float(max_gap_raw)
    except (TypeError, ValueError):
        max_gap = 0.005

    start = parse_start(scenario.start)
    stop_log = _capture_root_log()
    model = registry = None
    num_solutions = 0
    cbc_log = ""
    reads: set[str] = set()
    module_dir: Path | None = None
    prev_cwd = Path.cwd()
    exc: BaseException | None = None
    try:
        # _ensure_day_ahead_importable() puts dao/prog on sys.path, which
        # day_ahead.py needs for its own bare `from utils import (...)`.
        # DaCalc itself must come in via the *dotted* path, matching every
        # da_debug command and _import_targets()'s own patch targets — a
        # bare `import day_ahead` creates a second module object under a
        # different sys.modules key, and ReplayIO's CBC-log-capture patch
        # (installed on dao.prog.day_ahead) would silently miss it.
        da_debug._ensure_day_ahead_importable()
        from dao.prog.day_ahead import DaCalc
        import dao.prog.day_ahead as day_ahead_module

        # day_ahead.py's dispatch chart is written to a path relative to cwd
        # ("../data/images/..."), on the assumption that cwd is its own
        # directory (dao/prog) — the same assumption da_debug's own
        # capture/replay --png makes. Only relevant (and only done) when a
        # chart is actually being kept; every other write ReplayIO patches
        # away regardless of cwd.
        module_dir = Path(day_ahead_module.__file__).resolve().parent
        if keep_png:
            os.chdir(module_dir)

        tmp_opts = Path(tempfile.mkdtemp(prefix="dao-scenario-")) / "options.json"
        tmp_opts.write_text("{}")

        with da_debug.ReplayIO(snapshot, solver_threads=threads, png=keep_png) as replay:
            from dao.prog.da_base import DaBase

            replay._patches.set(
                DaBase, "calc_solar_predictions", _solar_patch(scenario)
            )
            dacalc = DaCalc(str(tmp_opts))
            dacalc._debug_capture_vars = True
            try:
                dacalc.calc_optimum(_start_dt=start)
            except da_debug.SnapshotMiss as miss:
                return ScenarioResult(
                    scenario.id, scenario.description, STATUS_ERROR,
                    failures=[f"replay hit a gap in the synthetic snapshot: {miss}"],
                    threads=threads,
                )
            model = replay._model
            registry = getattr(dacalc, "_debug_vars", None)
            num_solutions = model.num_solutions if model is not None else 0
            result_dict = replay.build_result()  # after calc_optimum() returns, per its own docstring
            cbc_log = (result_dict or {}).get("cbc_log") or ""
            reads = set(replay.reads)
    except BaseException as ex:  # noqa: BLE001
        exc = ex
    finally:
        if keep_png:
            os.chdir(prev_cwd)
        log_text = stop_log()

    if exc is not None:
        return ScenarioResult(
            scenario.id, scenario.description, STATUS_ERROR,
            failures=[f"solve raised {type(exc).__name__}: {exc}"], threads=threads,
        )

    objective = None
    if model is not None and num_solutions > 0:
        objective = model.objective_value

    png_path = None
    if keep_png and model is not None and module_dir is not None:
        candidate = _expected_png_path(module_dir, start)
        if candidate.exists():
            if report_dir is not None:
                report_dir.mkdir(parents=True, exist_ok=True)
                dest = report_dir / f"{scenario.id}.png"
                shutil.move(str(candidate), str(dest))
                png_path = str(dest)
            else:
                png_path = str(candidate)

    log_path = None
    if report_dir is not None and (log_text or cbc_log):
        report_dir.mkdir(parents=True, exist_ok=True)
        dest = report_dir / f"{scenario.id}.log"
        header = (
            f"scenario {scenario.id}  threads={threads}  objective={objective}\n"
            f"{'=' * 72}\n"
        )
        body = (
            header
            + "-- python log " + "-" * 58 + "\n" + log_text
            + "\n-- cbc log " + "-" * 61 + "\n" + (cbc_log or "(not captured)")
        )
        dest.write_text(body)
        log_path = str(dest)

    rc = ResultContext(model=model, registry=registry, log_text=log_text,
                       num_solutions=num_solutions)
    tier_a_checks = run_tier_a(rc)

    solved = next(c for c in tier_a_checks if c.name == "solved")
    if not solved.ok:
        return ScenarioResult(scenario.id, scenario.description, STATUS_INFEASIBLE,
                              objective=objective, checks=tier_a_checks,
                              failures=[f"[Tier A] solved: {solved.detail}"],
                              threads=threads, log_path=log_path, png_path=png_path)

    parsed_target = parsed_other = None
    if expanded_ev is not None:
        from .parsing import NOMINAL_MIN_DUTY, parse_ev_log

        parsed_target = parse_ev_log(log_text, expanded_ev.target_name, NOMINAL_MIN_DUTY)
        if expanded_ev.other_name:
            parsed_other = parse_ev_log(log_text, expanded_ev.other_name, NOMINAL_MIN_DUTY)

    requested_states = dict(scenario.states)
    if expanded_ev is not None:
        requested_states.update(expanded_ev.states)

    case_ctx = CaseContext(
        mv=rc.mv, scenario_id=scenario.id, start=start, horizon_hours=scenario.horizon_hours,
        objective=objective, max_gap=max_gap, reads=reads, requested_states=requested_states,
        config=config, expanded_ev=expanded_ev, parsed_target=parsed_target, parsed_other=parsed_other,
    )
    setup_checks = run_setup_checks(case_ctx)
    case_checks = run_case_checks(scenario.expect, case_ctx)
    checks = tier_a_checks + setup_checks + case_checks

    def _case_tag(name: str) -> str:
        # objective_within_baseline dispatches through the case-check
        # registry as an implementation detail — it's Tier C, not Tier B
        # (arch doc §6).
        return "[Tier C]" if name == "objective_within_baseline" else "[Tier B]"

    failures = (
        [f"[Tier A] {c.name}: {c.detail}" for c in tier_a_checks if not c.ok]
        + [f"[setup] {c.name}: {c.detail}" for c in setup_checks if not c.ok]
        + [f"{_case_tag(c.name)} {c.name}: {c.detail}" for c in case_checks if not c.ok]
    )
    status = STATUS_PASS if not failures else STATUS_FAIL

    from .parsing import parse_solve_stats

    stats = parse_solve_stats(log_text + "\n" + cbc_log)
    return ScenarioResult(scenario.id, scenario.description, status,
                          objective=objective, checks=checks, setup_checks=setup_checks,
                          failures=failures, threads=threads, log_path=log_path, png_path=png_path,
                          parsed_target=parsed_target, parsed_other=parsed_other, stats=stats)
