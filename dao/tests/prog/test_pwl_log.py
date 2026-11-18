"""Unit tests for ``_link_pwl``, the logarithmic (LogE) replacement of the
SOS2 sets in ``calc_optimum``.

* the rows for 5 breakpoints are exactly Huchette & Vielma,
  arXiv:1708.00050, eq. (3);
* for several curves, fixing x and minimising / maximising y gives the same
  result with ``_link_pwl`` as with the SOS2 definition itself (only two
  neighbouring weights nonzero, solved per pair of neighbours), for
  ``sum(w) == 1`` and ``sum(w) <= 1``;
* a gate fixed to 0 forces every weight to 0.

Skipped when ``mip`` is not installed.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]
_PROG_DIR = _REPO_ROOT / "dao" / "prog"
for _p in (str(_REPO_ROOT), str(_PROG_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

mip = pytest.importorskip("mip")
from mip import BINARY, CONTINUOUS, HIGHS, INTEGER, Model, OptimizationStatus, xsum  # noqa: E402

from dao.prog.day_ahead import _link_pwl  # noqa: E402

_OPTIONS_EXAMPLE = _REPO_ROOT / "dao" / "data" / "options_example.json"


def _new_model() -> Model:
    model = Model(solver_name=HIGHS)
    model.verbose = 0
    # HiGHS fixes its thread count per process at the first solve; day_ahead
    # and the scenario tests use 0 (automatic) or 1, so pin 1 here as well
    model.threads = 1
    return model


def _example_charge_curve() -> list[tuple[float, float]]:
    """The 13-point battery charge curve from options_example.json, as
    (AC kW, DC kW) like ``ac_to_dc_samples`` / ``dc_from_ac_samples``."""
    with open(_OPTIONS_EXAMPLE, encoding="utf-8") as f:
        stages = json.load(f)["battery"][0]["charge stages"]
    return [
        (st["power"] / 1000, st["power"] * st["efficiency"] / 1000) for st in stages
    ]


def _loss_discharge_curve() -> list[tuple[float, float]]:
    """6 points, AC out -> DC in with a fixed loss: nonconvex near 0 W."""
    powers = [0.0, 0.1, 0.5, 1.5, 3.0, 6.0]
    return [(p, 0.0 if p == 0 else p + 0.15 + 0.02 * p + 0.003 * p * p) for p in powers]


_CURVES = {
    "2pt": [(0.0, 0.0), (2.0, 1.8)],
    "3pt": [(0.0, 0.0), (1.0, 0.6), (3.0, 2.9)],
    "6pt": _loss_discharge_curve(),
    "13pt": _example_charge_curve(),
}


# --- paper check -------------------------------------------------------------


def _rows(model: Model) -> set:
    """Each row as (frozenset((var name, coef)), sense, rhs)."""
    out = set()
    for constr in model.constrs:
        expr = constr.expr
        terms = frozenset(
            (var.name, round(coef, 12)) for var, coef in expr.expr.items() if coef != 0
        )
        out.add((terms, expr.sense, round(-expr.const, 12)))
    return out


def test_rows_match_huchette_vielma_eq3():
    model = _new_model()
    lam = [model.add_var(name=f"lam{i}", lb=0, ub=1) for i in range(1, 6)]
    _link_pwl(model, lam, exact=True)
    extra = [v for v in model.vars if v.name not in {x.name for x in lam}]
    assert len(extra) == 2
    # HiGHS has no binary type: python-mip reads a BINARY back as INTEGER 0..1
    assert all(v.var_type in (BINARY, INTEGER) and (v.lb, v.ub) == (0, 1) for v in extra)
    y1, y2 = extra[0].name, extra[1].name

    # LogE rows, normalised to "expr <= rhs" with all variables on the left
    expected = {
        (frozenset({(f"lam{i}", 1.0) for i in range(1, 6)}), "=", 1.0),
        # λ3 <= y1
        (frozenset({("lam3", 1.0), (y1, -1.0)}), "<", 0.0),
        # λ1 + λ5 <= 1 - y1
        (frozenset({("lam1", 1.0), ("lam5", 1.0), (y1, 1.0)}), "<", 1.0),
        # λ4 + λ5 <= y2
        (frozenset({("lam4", 1.0), ("lam5", 1.0), (y2, -1.0)}), "<", 0.0),
        # λ1 + λ2 <= 1 - y2
        (frozenset({("lam1", 1.0), ("lam2", 1.0), (y2, 1.0)}), "<", 1.0),
    }
    assert _rows(model) == expected


# --- equivalence with SOS2 ---------------------------------------------------


def _build(curve, exact: bool, pair: int | None):
    """pair=None: the weights linked by _link_pwl. pair=j: the SOS2 reference
    for one pair of neighbours, every weight except w[j] and w[j + 1] fixed
    to 0. HiGHS has no SOS2, so the reference takes the best result over all
    pairs instead of an add_sos set."""
    model = _new_model()
    w = [model.add_var(var_type=CONTINUOUS, lb=0, ub=1) for _ in curve]
    x = model.add_var(lb=-1e3, ub=1e3)
    y = model.add_var(lb=-1e3, ub=1e3)
    model += xsum(w[k] * curve[k][0] for k in range(len(curve))) == x
    model += xsum(w[k] * curve[k][1] for k in range(len(curve))) == y
    if pair is None:
        _link_pwl(model, w, exact=exact)
    else:
        if exact:
            model += xsum(w) == 1
        else:
            model += xsum(w) <= 1
        for k in range(len(curve)):
            if k not in (pair, pair + 1):
                w[k].ub = 0
    return model, x, y


def _interpolate(curve, x_val: float) -> float:
    for (x1, y1), (x2, y2) in zip(curve, curve[1:], strict=False):
        if x1 <= x_val <= x2:
            return y1 + (y2 - y1) * (x_val - x1) / (x2 - x1)
    raise ValueError(x_val)


def _solve_y(curve, exact: bool, pair: int | None, x_val: float, sense: str) -> float | None:
    model, x, y = _build(curve, exact, pair)
    x.lb = x.ub = x_val
    model.objective = y
    model.sense = sense
    status = model.optimize()
    if pair is not None and status == OptimizationStatus.INFEASIBLE:
        return None  # x_val is not reachable on this pair of neighbours
    assert status == OptimizationStatus.OPTIMAL, (x_val, pair, sense, status)
    return y.x


def _y_range(curve, exact: bool, use_sos: bool, x_val: float) -> tuple[float, float]:
    if not use_sos:
        return (
            _solve_y(curve, exact, None, x_val, mip.MINIMIZE),
            _solve_y(curve, exact, None, x_val, mip.MAXIMIZE),
        )
    pairs = range(len(curve) - 1) if len(curve) > 1 else [0]
    lows = [_solve_y(curve, exact, j, x_val, mip.MINIMIZE) for j in pairs]
    highs = [_solve_y(curve, exact, j, x_val, mip.MAXIMIZE) for j in pairs]
    lows = [v for v in lows if v is not None]
    highs = [v for v in highs if v is not None]
    assert lows and highs, x_val
    return min(lows), max(highs)


@pytest.mark.parametrize("exact", [True, False], ids=["eq1", "le1"])
@pytest.mark.parametrize("curve_id", list(_CURVES))
def test_equivalent_to_sos2(curve_id, exact):
    curve = _CURVES[curve_id]
    rng = random.Random(f"{curve_id}-{exact}")
    x_min = curve[0][0] if exact else min(0.0, curve[0][0])
    x_max = curve[-1][0]
    xs = [pt[0] for pt in curve] + [rng.uniform(x_min, x_max) for _ in range(20)]

    for x_val in xs:
        lo_sos, hi_sos = _y_range(curve, exact, True, x_val)
        lo_log, hi_log = _y_range(curve, exact, False, x_val)
        assert lo_log == pytest.approx(lo_sos, abs=1e-6), x_val
        assert hi_log == pytest.approx(hi_sos, abs=1e-6), x_val
        if exact:
            y_ref = _interpolate(curve, x_val)
            assert lo_sos == pytest.approx(y_ref, abs=1e-6), x_val
            assert hi_sos == pytest.approx(y_ref, abs=1e-6), x_val


# --- gate --------------------------------------------------------------------


def test_gate_zero_forces_weights_to_zero():
    model = _new_model()
    w = [model.add_var(lb=0, ub=1) for _ in range(6)]
    gate = model.add_var(var_type=BINARY, lb=0, ub=0)
    _link_pwl(model, w, exact=True, gate=gate)
    for k in range(len(w)):
        model.objective = w[k]
        model.sense = mip.MAXIMIZE
        assert model.optimize() == OptimizationStatus.OPTIMAL
        assert w[k].x == pytest.approx(0.0, abs=1e-9)
