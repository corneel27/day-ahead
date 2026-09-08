"""Declarative scenario suite for ``DaCalc.calc_optimum()``.

A *scenario* is a small JSON object — a solve anchor, an hourly price array,
an optional hourly solar array, a handful of Home Assistant entity
overrides, and a list of expectations. The runner turns it into a synthetic
``da_debug.ReplayIO`` snapshot (built on top of ``dao/data/options_example.json``),
solves it hermetically with no database / Home Assistant / wall clock, and
checks the expectations.

Nothing here is reachable from an ordinary optimisation run. ``da_debug``
grows a ``scenario`` subcommand that drives this package; a thin pytest
wrapper (``dao/tests/prog/test_scenarios.py``) runs the same code in CI.

See ``dao_scenario_suite_plan.md`` for the design. This is session S1:
the synthetic builder, the loader/vocabulary, and the runner with the
Tier A structural invariants only.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CASES_DIR = PACKAGE_DIR / "cases"
BASELINES_DIR = PACKAGE_DIR / "baselines"
BASE_STATES_PATH = PACKAGE_DIR / "base_states.json"


def load_all(cases_dir: Path | None = None):
    """Every scenario across every ``cases/*.json`` file, id-checked for
    uniqueness. Imported lazily by callers so importing this package stays
    free of pandas / the solver."""
    from .loader import load_cases_dir

    return load_cases_dir(cases_dir or CASES_DIR)


def load(ids, cases_dir: Path | None = None):
    """The scenarios whose id is in ``ids`` (order follows ``ids``)."""
    wanted = list(dict.fromkeys(ids))
    by_id = {s.id: s for s in load_all(cases_dir)}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise KeyError(f"unknown scenario id(s): {missing}")
    return [by_id[i] for i in wanted]
