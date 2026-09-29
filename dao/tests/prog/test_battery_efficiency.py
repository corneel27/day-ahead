"""Tests for the power-weighted averaging of a battery efficiency curve.

The value produced here prices the energy still stored in the battery at the end
of the optimization horizon (day_ahead.py, avg_eff_dc_to_ac). It must depend on
the shape of the curve, not on how finely that curve is tabulated in the
configuration file.
"""

import sys

sys.path.append("../../../dao/prog")
from dao.prog.utils import power_weighted_efficiency


def stages(*pairs):
    return [{"power": p, "efficiency": e} for p, e in pairs]


# A real Zendure Solarflow 3000 discharge curve, sampled densely at low power
# (nine of its fifteen operating points sit at or below 400 W).
SOLARFLOW = stages(
    (0, 1.0), (50, 0.6), (100, 0.745), (150, 0.804), (200, 0.842), (250, 0.868),
    (300, 0.888), (350, 0.9), (400, 0.906), (500, 0.922), (750, 0.938),
    (1000, 0.947), (1500, 0.948), (2000, 0.95), (2500, 0.945), (3000, 0.941),
)


def row_mean(curve):
    """The average this replaces: an unweighted mean over the table rows."""
    return sum(s["efficiency"] for s in curve[1:]) / (len(curve) - 1)


def subdivide(curve):
    """Same curve, twice as many rows: a midpoint added to every real segment.

    The zero-power sentinel is left alone; a midpoint between it and the first
    operating point would be a new operating point, not a finer description of
    an existing one.
    """
    sentinel = [s for s in curve if s["power"] <= 0]
    points = [s for s in curve if s["power"] > 0]
    out = [points[0]]
    for low, high in zip(points, points[1:]):
        out.append(
            {
                "power": (low["power"] + high["power"]) / 2,
                "efficiency": (low["efficiency"] + high["efficiency"]) / 2,
            }
        )
        out.append(high)
    return sentinel + out


def test_lands_in_the_operating_range_not_on_the_table():
    # The row mean is dragged to 0.876 by the low-power rows; the weighted mean
    # sits near where the inverter actually runs (0.941-0.950 above 1 kW).
    assert abs(row_mean(SOLARFLOW) - 0.876) < 0.001
    assert abs(power_weighted_efficiency(SOLARFLOW) - 0.930) < 0.001


def test_invariant_under_subdivision():
    """Describing the same curve with more rows must not move the result."""
    once = subdivide(SOLARFLOW)
    twice = subdivide(once)
    base = power_weighted_efficiency(SOLARFLOW)
    assert len(twice) > 3 * len(SOLARFLOW)
    assert abs(power_weighted_efficiency(once) - base) < 1e-12
    assert abs(power_weighted_efficiency(twice) - base) < 1e-12


def test_row_mean_is_not_invariant_under_subdivision():
    """Guards the regression this replaces: the old average drifts on the edit above."""
    assert abs(row_mean(subdivide(SOLARFLOW)) - row_mean(SOLARFLOW)) > 1e-4


def test_trimming_the_low_power_rows_moves_it_far_less_than_the_row_mean():
    trimmed = stages(
        *[(s["power"], s["efficiency"]) for s in SOLARFLOW if s["power"] not in (50, 100)]
    )
    weighted_shift = abs(power_weighted_efficiency(trimmed) - power_weighted_efficiency(SOLARFLOW))
    row_shift = abs(row_mean(trimmed) - row_mean(SOLARFLOW))
    assert weighted_shift < 0.01          # only the integration bound moves
    assert row_shift > 0.03               # the row mean jumps by 3.1 points
    assert weighted_shift < row_shift / 4


def test_constant_curve_returns_that_constant():
    assert power_weighted_efficiency(stages((0, 1.0), (500, 0.9), (3000, 0.9))) == 0.9


def test_linear_curve_returns_its_midpoint():
    assert power_weighted_efficiency(stages((0, 1.0), (1000, 0.8), (3000, 1.0))) == 0.9


def test_zero_power_sentinel_is_ignored():
    with_sentinel = stages((0, 1.0), (1000, 0.9), (2000, 0.95))
    without_sentinel = stages((1000, 0.9), (2000, 0.95))
    assert power_weighted_efficiency(with_sentinel) == power_weighted_efficiency(
        without_sentinel
    )


def test_single_operating_point():
    assert power_weighted_efficiency(stages((0, 1.0), (2000, 0.93))) == 0.93


def test_no_operating_point_at_all():
    assert power_weighted_efficiency(stages((0, 1.0))) == 1.0
    assert power_weighted_efficiency([]) == 1.0


def test_duplicate_powers_do_not_divide_by_zero():
    assert power_weighted_efficiency(stages((0, 1.0), (500, 0.9), (500, 0.92))) == 0.91
