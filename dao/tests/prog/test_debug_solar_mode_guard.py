"""
Tests for the guard on the weather source behind a cached solar prediction.

The debug harness caches ``predict_solar_device()`` results per device name
only, on purpose: the start and end of the window drift between a run and the
capture around it. ``prefer_measured`` shares that key but does change the
answer, because it swaps the forecast irradiance for the measured one. Two
calls for one device that disagree on it would silently share a single cached
result, so the clash is refused on both the recording and the replay side.

Only ``calc_optimum()`` is ever captured today and it leaves the flag False
throughout, so this cannot currently fire. It closes the trap for whenever the
report path, the one caller that passes True, is brought under capture.
"""

import pytest

from dao.prog.da_debug import _solar_mode_conflict


def test_an_unrecorded_mode_is_not_a_conflict():
    """A snapshot captured before the mode was stored has nothing to check."""
    assert _solar_mode_conflict(None, False, "Zuid") is None
    assert _solar_mode_conflict(None, True, "Zuid") is None


@pytest.mark.parametrize("mode", [False, True])
def test_the_same_mode_twice_is_not_a_conflict(mode):
    assert _solar_mode_conflict(mode, mode, "Zuid") is None


@pytest.mark.parametrize(
    ("recorded", "requested"), [(False, True), (True, False)]
)
def test_a_differing_mode_is_reported(recorded, requested):
    message = _solar_mode_conflict(recorded, requested, "Zuid")
    assert message is not None
    # the device has to be named: a snapshot can hold several
    assert "Zuid" in message
    assert f"prefer_measured={recorded}" in message
    assert f"prefer_measured={requested}" in message


def test_the_comparison_survives_a_json_round_trip():
    """A hand-edited snapshot may carry 0/1 where a bool was written."""
    assert _solar_mode_conflict(0, False, "Zuid") is None
    assert _solar_mode_conflict(1, True, "Zuid") is None
    assert _solar_mode_conflict(0, True, "Zuid") is not None
