"""pytest entry point for the declarative scenario suite.

The runner, the synthetic-snapshot builder and the Tier A invariants live in
``dao/prog/scenarios/`` (shipped with the addon, driven by
``python -m dao.prog.da_debug scenario-run``). This file is a thin wrapper:

* solver-free unit tests for the vocabulary / loader / plugin registry —
  always run, in well under a second;
* one ``test_scenario[<id>]`` per corpus scenario that builds a synthetic
  snapshot, solves it hermetically and asserts the Tier A invariants —
  skipped unless ``mip`` is importable *and* ``DAO_RUN_SCENARIOS`` is set,
  so a machine without the solver still gets the unit coverage.

See ``dao_scenario_suite_plan.md`` (session S1).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]
_PROG_DIR = _REPO_ROOT / "dao" / "prog"
for _p in (str(_REPO_ROOT), str(_PROG_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dao.prog.scenarios import loader, plugins  # noqa: E402
from dao.prog.scenarios.loader import (  # noqa: E402
    ScenarioLoadError,
    parse_scenario,
    set_dotted,
)
from dao.prog.scenarios.vocabulary import (  # noqa: E402
    VocabularyError,
    parse_start,
    upsample,
)


def _solver_ready() -> bool:
    if os.environ.get("DAO_RUN_SCENARIOS", "").strip() in ("", "0", "false"):
        return False
    try:
        import mip  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


_SKIP = pytest.mark.skipif(
    not _solver_ready(),
    reason="set DAO_RUN_SCENARIOS=1 (and install mip) to run the solving scenario tests",
)


# ---------------------------------------------------------------------------
# solver-free unit coverage
# ---------------------------------------------------------------------------


def test_parse_start_grid_and_errors():
    assert parse_start("2026-01-14 07:00").hour == 7
    assert parse_start("2026-01-14T07:15:00").minute == 15
    with pytest.raises(VocabularyError):
        parse_start("2026-01-14 07:07")          # off the 15-min grid
    with pytest.raises(VocabularyError):
        parse_start("not a date")


def test_upsample_repeats_and_truncates():
    out = upsample([1.0, 2.0, 3.0], horizon_hours=2, label="x")
    assert out == [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0]   # ×4, truncated to 2 h
    with pytest.raises(VocabularyError):
        upsample([1.0], horizon_hours=3, label="x")           # too short
    with pytest.raises(VocabularyError):
        upsample([], horizon_hours=1, label="x")


def test_set_dotted_nested_and_indexed():
    tree = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    set_dotted(tree, "a.b[1].c", 9)
    set_dotted(tree, "a.b[0].c", 0)
    assert tree == {"a": {"b": [{"c": 0}, {"c": 9}]}}


def test_loader_accepts_a_minimal_scenario():
    s = parse_scenario({
        "id": "u1", "description": "d", "start": "2026-01-14 07:00",
        "prices": {"cons": [0.3, 0.3]},
        "expect": {"solved": True},
    }, source_file="unit.json")
    assert s.horizon_hours == 2 and s.prices_prod is None and s.solar is None


@pytest.mark.parametrize("bad, needle", [
    ({"id": "x", "description": "d", "start": "2026-01-14 07:00"}, "prices"),
    ({"id": "x", "description": "d", "start": "2026-01-14 07:00",
      "prices": {"cons": [0.3, 0.3]}, "expect": {"bogus_key": True}}, "expect key"),
    ({"id": "x", "description": "d", "start": "2026-01-14 07:07",
      "prices": {"cons": [0.3, 0.3]}}, "15-minute"),
    ({"id": "x", "description": "d", "start": "2026-01-14 07:00",
      "prices": {"cons": [0.3, 0.3]}, "solar": ["sunny"]}, "list of numbers"),
    ({"id": "x", "description": "d", "start": "2026-01-14 07:00",
      "prices": {"cons": [0.3, 0.3]}, "nope": 1}, "unknown scenario key"),
])
def test_loader_rejects_malformed(bad, needle):
    with pytest.raises(ScenarioLoadError) as ei:
        parse_scenario(bad)
    assert needle in str(ei.value)


def test_loader_rejects_duplicate_ids(tmp_path):
    (tmp_path / "a.json").write_text(
        '[{"id":"dup","description":"d","start":"2026-01-14 07:00","prices":{"cons":[0.3,0.3]}}]')
    (tmp_path / "b.json").write_text(
        '[{"id":"dup","description":"d","start":"2026-01-14 07:00","prices":{"cons":[0.3,0.3]}}]')
    with pytest.raises(ScenarioLoadError) as ei:
        loader.load_cases_dir(tmp_path)
    assert "duplicate scenario id 'dup'" in str(ei.value)


def test_plugin_registry_round_trip():
    @plugins.plugin("_unit_probe")
    def _probe(ctx, *, k):  # noqa: ARG001
        return k * 2

    assert plugins.get_plugin("_unit_probe")(None, k=3) == 6
    assert "_unit_probe" in plugins.registered()
    with pytest.raises(KeyError):
        plugins.get_plugin("_nope")


def test_corpus_loads_with_unique_ids():
    from dao.prog.scenarios import load_all

    ids = [s.id for s in load_all()]
    assert ids and len(ids) == len(set(ids))


def test_tier_a_stops_after_solved_fails_on_no_solution():
    """An infeasible solve leaves var.x as None. Tier A must report the
    'solved' failure and not run the invariants that compare var.x."""
    from types import SimpleNamespace

    from dao.prog.scenarios.expectations import ResultContext, run_tier_a

    names = ["ac_to_dc_on", "ac_from_dc_on", "soc"]
    by_idx = {i: (name, (0, 0)) for i, name in enumerate(names)}
    model = SimpleNamespace(vars=[SimpleNamespace(x=None, lb=0.0, ub=1.0) for _ in names])
    rc = ResultContext(
        model=model,
        registry=SimpleNamespace(by_idx=by_idx, samples={}),
        log_text="",
        num_solutions=0,
    )

    checks = run_tier_a(rc)

    assert [c.name for c in checks] == ["solved"]
    assert not checks[0].ok
    assert "model has no solution" in checks[0].detail


def _fake_boiler_rc(*, c_b1=0.375, temp1=43.0, log_text=""):
    """A 3-interval multi-start boiler plan: a cycle starts at u1 at full
    power and finishes at u2, ending at the 50 C setpoint."""
    from types import SimpleNamespace

    from dao.prog.scenarios.expectations import ResultContext

    full = 0.375
    containers = {
        "boiler_start": [(0, 0, 1), (1, 0, 1), (0, 0, 1)],
        "boiler_heat": [(0, 0, 1), (1, 0, 1), (1, 0, 1)],
        "boiler_finish": [(0, 0, 1), (0, 0, 1), (1, 0, 1)],
        "c_b": [(0.0, 0, full), (c_b1, 0, full), (0.1, 0, full)],
        "boiler_temp": [(45.0, 40, 50), (temp1, 40, 50), (48.0, 40, 50), (50.0, 40, 50)],
    }
    model_vars, by_idx = [], {}
    for name, values in containers.items():
        for u, (x, lb, ub) in enumerate(values):
            by_idx[len(model_vars)] = (name, (u,))
            model_vars.append(SimpleNamespace(x=x, lb=lb, ub=ub))
    return ResultContext(
        model=SimpleNamespace(vars=model_vars),
        registry=SimpleNamespace(by_idx=by_idx, samples={}),
        log_text=log_text,
        num_solutions=1,
        config={"boiler": {"heating_allowed_below": {"value": 44}}},
    )


def test_boiler_cycle_consistent_accepts_a_valid_cycle():
    from dao.prog.scenarios.expectations import BoilerCycleConsistent

    assert BoilerCycleConsistent().check(_fake_boiler_rc()).ok


@pytest.mark.parametrize("kwargs, needle", [
    ({"c_b1": 0.2}, "not full power"),
    ({"temp1": 46.0}, "> heating limit"),
])
def test_boiler_cycle_consistent_flags_broken_cycles(kwargs, needle):
    from dao.prog.scenarios.expectations import BoilerCycleConsistent

    result = BoilerCycleConsistent().check(_fake_boiler_rc(**kwargs))
    assert not result.ok
    assert needle in result.detail


def test_boiler_trigger_reported_needs_the_planned_line():
    from dao.prog.scenarios.expectations import (
        BOILER_PLANNED_LINE,
        BoilerTriggerReported,
    )

    # c_b[0] == 0, so no trigger line; the plan has a start at u1
    assert not BoilerTriggerReported().check(_fake_boiler_rc()).ok
    assert BoilerTriggerReported().check(_fake_boiler_rc(log_text=BOILER_PLANNED_LINE)).ok


def test_no_unexpected_error_flags_the_output_except():
    from dao.prog.scenarios.expectations import NoUnexpectedError, ResultContext

    rc = ResultContext(model=None, registry=None, num_solutions=0,
                       log_text="ERROR Onverwachte fout: name 'x' is not defined")
    assert not NoUnexpectedError().check(rc).ok
    rc.log_text = "Grid set point: 0 W"
    assert NoUnexpectedError().check(rc).ok


def test_boiler_starts_counts_in_window_and_whole_horizon():
    import datetime as dt

    from dao.prog.scenarios.expectations import CaseContext, _check_boiler_starts

    rc = _fake_boiler_rc()
    start = dt.datetime(2026, 1, 14, 0, 0)
    grid = [start + dt.timedelta(minutes=15 * u) for u in range(3)]
    ctx = CaseContext(
        mv=rc.mv, scenario_id="t", start=start, horizon_hours=1, grid=grid,
        row_hours=[0.25] * 3, objective=None, max_gap=0.0, reads=set(),
        requested_states={},
    )
    assert _check_boiler_starts({"min": 1, "max": 1}, ctx).ok
    assert not _check_boiler_starts({"max": 0}, ctx).ok
    assert not _check_boiler_starts({"start": "00:00", "end": "00:15", "min": 1}, ctx).ok


# ---------------------------------------------------------------------------
# solving scenarios (opt-in)
# ---------------------------------------------------------------------------


def _corpus_ids():
    try:
        from dao.prog.scenarios import load_all

        return [s.id for s in load_all()]
    except Exception:  # noqa: BLE001 - collection must not hard-fail
        return []


@_SKIP
@pytest.mark.parametrize("scenario_id", _corpus_ids())
def test_scenario(scenario_id):
    from dao.prog.scenarios import load
    from dao.prog.scenarios.runner import run_scenario

    (scenario,) = load([scenario_id])
    result = run_scenario(scenario)
    assert result.ok, f"{result.status}: " + "; ".join(result.failures)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
