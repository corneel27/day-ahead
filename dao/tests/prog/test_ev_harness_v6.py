"""
Automated test harness for the EV charging test plan (day_ahead.py). v2.

WHAT THIS DOES
---------------
Runs the real `DaCalc.calc_optimum()` solver, once per test case, against
your real config/prices/battery — but with the EV-related HA entities
answered by canned values instead of by clicking through Home Assistant.
It does this by monkeypatching the single method everything reads through:
`self.get_state(entity_id).state`. Any entity_id not overridden for a given
test case still goes to your real `get_state`, so battery, prices, the
other EV, etc. behave exactly as they do in a normal manual run.

It parses the log output the solver already produces (the setup echo, the
"Inzet-factor laden ... per stop" table, and the summary lines under it)
and checks each case's pass criteria automatically. It also writes a
Markdown + CSV report to `test_reports/` when done.

NEW IN v2
----------
- SETUP-ECHO VERIFICATION. Before judging the model's decision, each case
  now checks that the overrides it sent actually show up in the log
  (Huidig laadniveau, Gewenst laadniveau, Locatie, Ingeplugged, Direct
  laden is, Klaar met laden op). If they don't match, the case is marked
  SETUP_MISMATCH instead of FAIL — because a mismatch means the override
  silently no-op'd (e.g. the entity is None / unconfigured for this EV),
  and judging the model's scheduling decision on top of that is
  meaningless. This is exactly what case 5.1 hit: `entity_instant_start`
  is apparently `None` for the Golf, so requesting instant-on silently did
  nothing and the model correctly evaluated instant_charge=False.
- Case 4.3 no longer uses a raw `now + 5 minutes` offset, NOR (as of this
  version) an end-anchored-only offset. Both were timing-fragile:
    - `now + 5 minutes`: depends on real wall-clock position within the
      15-minute grid, so the same "+5 min" can land anywhere from 1 to 14
      minutes before the interval boundary depending on when you run it.
    - anchoring only the ready deadline near the end of "the current
      interval": still depends on where real now() happens to sit when
      THIS SPECIFIC CASE executes within a longer run — by the time a
      15-case batch reaches case #12, now() could already be near the end
      of whatever interval it's in, shrinking the window right back down.
      This is exactly what happened in the first real run: 0.230 kWh
      achievable, still under the Golf's 1% margin (~0.363 kWh needed).
  The fix (`ready_u_zero_full_window`) pins BOTH start_dt and ready_dt from
  a single now() snapshot: start_dt = exact start of the current interval,
  ready_dt = just before its end. That gives a ~14-minute window
  independent of real wall-clock position, while still guaranteeing
  ready_u == 0.
- A test report (Markdown + CSV) is written after each run.
- Solve stats (nodes / gap in particular) were silently always "—" in the
  first real reports. Root cause: CBC's "Search completed... N nodes" and
  "Exiting as integer gap of G..." lines are native C-level solver output,
  never routed through Python's `logging` module, so `capture_log()` (a
  logging.Handler) never saw them — confirmed by grep: "Rekentijd" IS a
  `logging.info()` call in day_ahead.py (hence it always parsed), the CBC
  node/gap lines are not logging calls at all. Fixed with
  `capture_native_stdout()`, which redirects the OS-level stdout file
  descriptor (not just `sys.stdout`) for the duration of the solve.

NEW IN v3
----------
- Case 3.3 (day rollover): every other case sends the ready-datetime
  override as a full "YYYY-MM-DD HH:MM:SS" string, which only ever
  exercises day_ahead.py's `len(ready_str) > 9` branch. Nothing tested the
  short "%H:%M:%S" branch or its day-rollover arithmetic. `day_rollover_
  ready_time()` pins start_dt to 23:15 today and sends a short early-morning
  time, forcing the source to resolve it against tomorrow's date.
  `_predict_ready_rollover()` mirrors that exact algorithm (including its
  coarse hour-then-minute comparison and second-dropping) so the existing
  setup-echo verification catches it immediately if the resolved date is
  ever wrong, off by a day, or silently not rolled over.
- Case 6.7 (two EVs simultaneously): both cars get real, independent
  charging needs instead of the default away/unplugged "other_input" — a
  regression test for a previously-fixed cross-EV bug. Two mechanisms now
  apply to EVERY case, not just 6.7, since they're cheap and directly test
  for the same class of leak:
    - `check_capacity()` compares each EV's echoed "Capaciteit accu" against
      its known value (Golf 36.3 / Tesla 55.0). A mismatch means one EV's
      log block shows the OTHER car's config — folded into SETUP_MISMATCH.
    - the "other" EV's exclusivity (multi_stage_intervals) is now checked
      on every case, not only when it's the case's deliberate focus.
  `other_expect_scheduled` lets a case additionally assert the non-target
  EV's scheduling outcome (used by 6.7; None elsewhere, meaning unchecked).

NEW IN v4
----------
- MINIMUM DUTY CYCLE (Section 7). day_ahead.py now forces every REAL charge
  stage to be either off or on for at least 300 s. Before that constraint,
  the LP could give a real stage a weight of ~0.003 — a one-second charge
  command — purely to land inside the +/-0.001 kWh `ev_energy_slack` band.
  That is legal under every other constraint and is NOT the multi-stage
  exclusivity bug (only one real stage is active), but it is not
  dispatchable: a contactor can't usefully close for a second, and
  `new_state_stop_laden` is formatted "%H:%M", which can't represent it.
  Like the multi-stage check, the sliver check now runs on EVERY case and on
  BOTH cars; Section 7 exists to make sure something actually walks into it.
- The comparison uses `nominal_min_duty()` = EV_MIN_DUTY_S / interval_s,
  which is a FLOOR on the model's true per-interval min_duty (that value is
  larger on the short first and last intervals). Deliberately conservative:
  it cannot produce a false positive, and can only under-report on those two
  intervals — the alternative was re-deriving day_ahead.py's interval
  alignment here, the same duplication that made early case 4.3 fragile.
- Two tolerances, both learned the hard way while testing the checker
  itself: DUTY_ZERO_TOL separates "off" from "sliver", and
  DUTY_COMPARE_TOL exists because a legal factor of exactly 1/3 is LOGGED as
  "0.3333" — without it, every correctly-constrained minimum-duty interval
  would be reported as a violation.
- `soc_factory` / `remainder_soc_factory()`: Section 7's cases must derive
  their SoC pair backwards from the car's own top-stage delivery, so that
  energy_needed is N full intervals plus a remainder too small to deliver in
  one 5-minute action. Hardcoded percentages would provoke a sliver only by
  luck, since an arbitrary remainder is uniformly distributed.
- `expect_partial_at_least`: Section 7's cases are NEGATIVE tests, so if the
  engineered remainder ever stops landing partway through an interval they
  would pass while testing nothing. This fails them loudly instead. The
  count is stable across the fix — the remainder interval is partial either
  way, only its size changes.
- Report gains a "Min factor" column plus `duty_slivers`,
  `min_nonzero_factor` and `min_duty_guard_fired` in the CSV.

NEW IN v5
----------
- RETUNED 7.1/7.2/7.4 (Golf, non-monotonic curve). A min_duty_s=0 control
  run showed these three barely moved between fix-on and fix-off — min
  factor 0.9998 on 7.2, near-unchanged on 7.1/7.4 — meaning the Golf's curve
  let the solver absorb the engineered remainder via stage substitution
  (switching amperage for a whole interval) instead of a short duty cycle,
  so the minimum-duty constraint was never actually being exercised on
  these three. 7.3/7.5 (Tesla, monotone curve — no substitution option) DID
  show clear slivers under the same control run, which is what exposed the
  gap: it wasn't the assertion that was wrong, it was that these three
  cases weren't reaching the code path they claim to test.
  `remainder_kwh` raised from 0.02-0.04 kWh to 0.20-0.24 kWh on all three,
  still under the Golf's ~0.28 kWh single-switch floor (lowest stage's
  accu_power * 300s), to make duty-cycling cheaper than substitution.
  Before trusting these again: re-run with min_duty_s=0 and confirm they
  now fail with reported slivers the way 1.T/7.3/7.5 did; only then re-run
  at the real min_duty_s and confirm clean.

NEW IN v6
----------
- BUG 7 REGRESSION (Section 5). day_ahead.py reads entity_ready_datetime
  and derives hours_avail *unconditionally*, before instant_charge is ever
  consulted — that value then feeds the "te weinig tijd" clamp
  (`e_needed > max_possible` -> wished_level pulled down toward whatever's
  reachable by that deadline). Nothing in that clamp checks instant_charge,
  so a tight or stale entity_ready_datetime can silently undercharge an
  instant-charge request. 5.1 never actually exercised this: it pins
  ready_dt 8 hours out, so hours_avail was always generous and the clamp
  had no reason to fire — a PASS there says nothing about the bug either
  way. New case 5.2 pins ready_dt to +15 minutes instead, which should
  provoke the clamp hard (well under 1 kWh reachable vs. ~25.4 kWh needed)
  if the bug is live, and both cases now assert
  expect_wished_level_clipped=False so the clamp firing is a hard FAIL
  instead of a silent, invisible pass.
- New `wished_level_clipped` signal, parsed from the "Er is te weinig
  tijd" log line within the same per-EV setup block already used for
  `energy_needed_kwh` (so it's scoped by EV name the same way). Asserted
  via `expect_wished_level_clipped`; also written to the CSV for any case
  that doesn't assert it, the same way `min_nonzero_factor` is reported
  without being asserted everywhere.
- Do not trust a PASS on an instant-charge case as evidence about Bug 7
  unless you've checked that case actually controls ready_dt to something
  short. A generous or unset ready_dt (leaving the real HA entity alone)
  makes the case blind to this bug by construction — confirmed the hard
  way: an earlier run's raw log showed "Klaar met laden op: 25-07-2026
  21:58:28" for 5.1, consistent with its own pinned +8h window, not with
  whatever the live entity_ready_datetime happened to hold at the time.

WHAT THIS DOES NOT DO
----------------------
It does not fabricate price or battery data — those still come from your
live setup, so run this on a day where day-ahead prices are actually
loaded, same as a manual debug run. It also doesn't replace judgement on
the "known issues, observe don't chase" section of the test plan — those
are printed but not failed.

SAFETY: WHY THIS FORCES self.debug = True
-------------------------------------------
`self.debug` isn't only a logging flag — it also gates every real write to
Home Assistant in the EV dispatch block (`set_value`, `turn_on`, `turn_off`,
`call_service`, plus a couple of prognosis-saving calls earlier). With
debug=False those calls execute for real. `calc_optimum_debug()` sets
`self.debug = True` for you, but it's a zero-argument wrapper around
`calc_optimum()` and can't accept the `_start_dt` this harness needs per
case. So `run_case()` sets `da_calc.debug = True` itself, immediately before
every solve call — this is not optional, it's what keeps this script from
actually toggling your chargers. If you ever change `run_case()`, keep that
line.

SETUP REQUIRED FROM YOU
-------------------------
1. Set EV_INDEX_TESLA / EV_INDEX_GOLF below (or leave the name-matching
   autodetect, see `_find_ev_index`).
2. Confirm `import` path / working directory matches how you normally run
   day_ahead.py (this assumes it's importable as `day_ahead`).
3. Case 4.4/4.5 mutate `entity_stop_charging` on the live config object and
   restore it afterwards. If `ev_options[e]` is a frozen pydantic model,
   direct attribute assignment will raise — see `_with_stop_entity_removed`
   for the fallback path, and adjust it to match your actual config class
   if needed (I could not see da_base.py / the config schema from here).
4. If 5.1 still shows SETUP_MISMATCH after this update: `entity_instant_start`
   is genuinely unconfigured for the Golf in your options.json. Either add
   it there, or retarget that case at the Tesla (change target="tesla").

Run:
    python test_ev_harness.py
"""

from __future__ import annotations

import csv
import ctypes
import datetime as dt
import io
import logging
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from day_ahead import DaCalc  # adjust import if your entrypoint differs

CONFIG_PATH = "../data/options.json"  # matches main() in day_ahead.py
REPORT_DIR = Path("test_reports")

# --- minimum duty cycle (see EV handover addendum, §19 under Bug 2) ---------
# day_ahead.py constrains every REAL charge stage (cs >= 1) to be either off
# or on for at least EV_MIN_DUTY_S seconds, via
#     stage_factor[e][cs][u] >= min_duty * stage_on[e][cs][u]
# with min_duty = min(1.0, EV_MIN_DUTY_S / (hr_fraction * 3600)).
# Keep this in sync with `ev_min_duty_s` in day_ahead.py.
EV_MIN_DUTY_S = 300.0

# Tolerance below which a stage_factor is treated as "off" rather than as a
# sliver. The factor table is logged to 4 decimals, so anything at or under
# 1e-4 is indistinguishable from zero in the parsed output anyway.
DUTY_ZERO_TOL = 1e-4

# Slack when comparing a factor against min_duty. Two effects stack here and
# both are one-sided against us:
#   - the factor table is logged to 4 decimals, so a legal value of exactly
#     1/3 prints as "0.3333", which is BELOW min_duty by 3.3e-5;
#   - CBC satisfies constraints to its own feasibility tolerance, so a
#     legal value can sit a hair under the bound in the solution itself.
# Without this slack, every correctly-constrained interval at exactly the
# minimum duty would be reported as a violation. 1e-4 is four orders of
# magnitude below a real sliver (~0.003 against a min_duty of 0.333), so it
# costs no detection power.
DUTY_COMPARE_TOL = 1e-4

_libc = ctypes.CDLL(None)

# ---------------------------------------------------------------------------
# Fake HA state plumbing
# ---------------------------------------------------------------------------


class FakeState:
    """Mimics whatever object self.get_state(...) normally returns — only
    `.state` is ever read in the EV code path."""

    def __init__(self, value):
        self.state = str(value)


@contextmanager
def get_state_overrides(da_calc: DaCalc, overrides: dict[str, object]):
    """Temporarily replace da_calc.get_state so that entity_ids in
    `overrides` return canned values, and everything else still hits the
    real get_state. Restores the original method on exit even if the run
    raises."""
    real_get_state = da_calc.get_state

    def patched(entity_id, *args, **kwargs):
        if entity_id in overrides:
            return FakeState(overrides[entity_id])
        return real_get_state(entity_id, *args, **kwargs)

    da_calc.get_state = patched
    try:
        yield
    finally:
        da_calc.get_state = real_get_state


@contextmanager
def capture_log():
    """Capture everything logged during the run (same records that go to
    your console/log file) into a StringIO, INFO and above, then remove
    the handler afterwards."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(min(prev_level, logging.INFO))
    root.addHandler(handler)
    try:
        yield buf
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)


@contextmanager
def capture_native_stdout():
    """Captures OS-level file descriptor 1 (real stdout), which is what
    CBC's native solver actually writes to via its own C-level printf-style
    calls. These lines never pass through Python's `logging` module, so
    `capture_log()` — a logging.Handler — is structurally blind to them.
    This is confirmed by grepping day_ahead.py: "Rekentijd" is a
    logging.info() call (hence it parses fine), but "Cbc0001I Search
    completed..." and "Cbc0011I Exiting as integer gap..." don't appear in
    any logging call in the file at all.

    Plain `contextlib.redirect_stdout` would NOT catch this — it only
    reassigns Python's `sys.stdout` object, and C extensions writing via
    native stdio bypass that entirely. This redirects the actual OS file
    descriptor instead, and explicitly flushes libc's stdio buffers with
    `fflush(NULL)` before restoring it, since output written to a
    non-tty (our temp file) is typically fully buffered rather than
    line-buffered and could otherwise sit unflushed in CBC's internal
    buffer past the point where we read it back — or worse, leak into the
    next test case's capture once eventually flushed.

    Usage: `with capture_native_stdout() as native: ...` then read
    `native["text"]` AFTER the with-block exits (it's populated in this
    generator's `finally`, which runs during `__exit__`, before control
    returns to the caller).
    """
    stdout_fd = 1
    saved_fd = os.dup(stdout_fd)
    tmp = tempfile.TemporaryFile(mode="w+b")
    _libc.fflush(None)
    os.dup2(tmp.fileno(), stdout_fd)
    result = {"text": ""}
    try:
        yield result
    finally:
        _libc.fflush(None)
        os.dup2(saved_fd, stdout_fd)
        os.close(saved_fd)
        tmp.seek(0)
        result["text"] = tmp.read().decode(errors="replace")
        tmp.close()


@contextmanager
def _with_stop_entity_removed(da_calc: DaCalc, ev_index: int):
    """Case 4.4/4.5 support: temporarily make entity_stop_charging look
    absent for one EV. Tries plain attribute assignment first (works if
    ev_options[e] is a plain object / mutable pydantic model). If that
    raises (frozen model), falls back to swapping in a shallow copy via
    model_copy — ADAPT THIS if your config class differs."""
    ev = da_calc.ev_options[ev_index]
    original = ev.entity_stop_charging
    try:
        ev.entity_stop_charging = None
        restore = lambda: setattr(ev, "entity_stop_charging", original)
    except Exception:
        new_ev = ev.model_copy(update={"entity_stop_charging": None})
        da_calc.ev_options[ev_index] = new_ev
        restore = lambda: da_calc.ev_options.__setitem__(ev_index, ev)
    try:
        yield
    finally:
        restore()


@contextmanager
def _null_ctx():
    yield


def _find_ev_index(da_calc: DaCalc, name_substring: str) -> int:
    for i, ev in enumerate(da_calc.ev_options):
        if name_substring.lower() in ev.name.lower():
            return i
    raise ValueError(f"No EV config found matching {name_substring!r}")


# ---------------------------------------------------------------------------
# Timing helper for case 4.3 (ready_u == 0), grid-anchored instead of
# wall-clock-offset
# ---------------------------------------------------------------------------


def ready_u_zero_full_window(
    buffer_seconds: int = 45,
) -> Callable[[DaCalc], tuple[dt.datetime, dt.datetime, Optional[str]]]:
    """Returns a factory (da_calc) -> (start_dt, ready_dt) for a ready_u==0
    test with a near-full interval's charging window, regardless of when
    in a multi-case run this particular case happens to execute.

    First attempt at this (anchoring only the ready deadline near the end
    of "the current interval") was NOT enough: by the time a later case in
    a run executes, real now() could already be sitting anywhere inside
    that interval — including near its own end — so the achievable window
    (ready - now) could still shrink to a couple of minutes by pure timing
    luck. That's what happened: 0.230 kWh needed, still under the 1%
    margin (which needs ~0.363 kWh / ~6.4 minutes at the Golf's max power
    to clear).

    The fix pins BOTH ends to the same interval, from a single now()
    snapshot: start_dt = the exact beginning of the interval now() is in,
    ready_dt = buffer_seconds before its end. That gives a ~14-minute
    window (at 900s intervals) independent of real wall-clock position,
    while still guaranteeing ready_u == 0 (ready falls inside the interval
    calc_optimum treats as u=0, since start_dt IS that interval's start).
    """

    def _factory(da_calc: DaCalc) -> tuple[dt.datetime, dt.datetime]:
        interval_s = da_calc.interval_s
        now_ts = int(dt.datetime.now().timestamp())
        start_of_interval_ts = interval_s * (now_ts // interval_s)
        end_of_interval_ts = start_of_interval_ts + interval_s
        start_dt = dt.datetime.fromtimestamp(start_of_interval_ts)
        ready_dt = dt.datetime.fromtimestamp(end_of_interval_ts - buffer_seconds)
        return start_dt, ready_dt, None

    return _factory


# ---------------------------------------------------------------------------
# Day-rollover helper for the short "HH:MM:SS" ready-datetime format
# ---------------------------------------------------------------------------


def _predict_ready_rollover(start_dt: dt.datetime, hh_mm_ss: str) -> dt.datetime:
    """Mirrors day_ahead.py's short-format ready-datetime parsing exactly
    (the `else` branch, len(ready_str) <= 9):

        ready = dt.datetime.strptime(ready_str, "%H:%M:%S")
        ready = dt.datetime(start_dt.year, start_dt.month, start_dt.day,
                             ready.hour, ready.minute)
        if (ready.hour == start_dt.hour and ready.minute < start_dt.minute) or (
            ready.hour < start_dt.hour
        ):
            ready = ready + dt.timedelta(days=1)

    Note the comparison is coarse (hour first, minute only as a tiebreak on
    equal hour) and seconds are dropped entirely — reproduced verbatim here
    so the harness predicts exactly what the source will compute, not an
    approximation of it.
    """
    t = dt.datetime.strptime(hh_mm_ss, "%H:%M:%S")
    ready = dt.datetime(start_dt.year, start_dt.month, start_dt.day, t.hour, t.minute)
    if (ready.hour == start_dt.hour and ready.minute < start_dt.minute) or (
        ready.hour < start_dt.hour
    ):
        ready = ready + dt.timedelta(days=1)
    return ready


def day_rollover_ready_time(
    hour: int = 1, minute: int = 0
) -> Callable[[DaCalc], tuple[dt.datetime, dt.datetime, str]]:
    """Returns a factory (da_calc) -> (start_dt, predicted_ready_dt,
    ready_override_str) that tests the SHORT ready-datetime format and its
    day-rollover arithmetic — a code path nothing in this suite exercised
    before, since every other case sends a full "YYYY-MM-DD HH:MM:SS"
    string (the `len(ready_str) > 9` branch). This deliberately targets the
    `else` branch and its rollover-to-tomorrow logic.

    start_dt is pinned to 23:15 on the current real calendar date — late
    enough that an early-morning `hour:minute` is unambiguously "earlier"
    by the source's own hour/minute comparison, and still today's date, so
    today's already-published day-ahead prices cover it. ready_override_str
    is a short "HH:MM:SS" string for the given hour/minute, which forces
    the model to resolve it against tomorrow's date — genuinely spanning
    midnight in the optimisation horizon, not just in the string parsing.
    """

    def _factory(da_calc: DaCalc) -> tuple[dt.datetime, dt.datetime, str]:
        today = dt.date.today()
        start_dt = dt.datetime(today.year, today.month, today.day, 23, 15)
        ready_override_str = f"{hour:02d}:{minute:02d}:00"
        predicted_ready = _predict_ready_rollover(start_dt, ready_override_str)
        return start_dt, predicted_ready, ready_override_str

    return _factory


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------

ReadyDtSpec = Union[dt.datetime, Callable[[DaCalc], dt.datetime], None]


@dataclass
class EvCaseInput:
    plugged_in: Optional[bool] = None
    position: Optional[str] = None  # "home" / "away"
    actual_soc: Optional[float] = None
    instant_charge: Optional[bool] = None
    wished_level: Optional[float] = None
    ready_dt: ReadyDtSpec = None  # None -> leave real entity alone
    # When set, this exact string is sent as the ready-datetime HA state
    # instead of formatting ready_dt as "%Y-%m-%d %H:%M:%S". Use for testing
    # the short "%H:%M:%S" parsing branch (day_ahead.py's len(ready_str) <= 9
    # path) — ready_dt should still be set (or resolved via dynamic_setup)
    # to the PREDICTED result, so setup-echo verification has something to
    # check against.
    ready_override_str: Optional[str] = None


@dataclass
class ResolvedEvInput:
    """Same shape as EvCaseInput but with ready_dt fully resolved to a
    concrete datetime (or None), so it can be reused both for building
    overrides and for verifying the log echo without calling a
    now()-dependent factory twice."""
    plugged_in: Optional[bool]
    position: Optional[str]
    actual_soc: Optional[float]
    instant_charge: Optional[bool]
    wished_level: Optional[float]
    ready_dt: Optional[dt.datetime]
    ready_override_str: Optional[str] = None


def _resolve(da_calc: DaCalc, inp: EvCaseInput) -> ResolvedEvInput:
    ready = inp.ready_dt(da_calc) if callable(inp.ready_dt) else inp.ready_dt
    return ResolvedEvInput(
        plugged_in=inp.plugged_in,
        position=inp.position,
        actual_soc=inp.actual_soc,
        instant_charge=inp.instant_charge,
        wished_level=inp.wished_level,
        ready_dt=ready,
        ready_override_str=inp.ready_override_str,
    )


@dataclass
class TestCase:
    id: str
    description: str
    target: str  # "tesla" or "golf" -- which EV_INDEX_* to use as the target
    target_input: EvCaseInput
    other_input: EvCaseInput = field(
        default_factory=lambda: EvCaseInput(plugged_in=False, position="away")
    )
    start_dt: Optional[dt.datetime] = None  # None -> now
    # For cases where start_dt and target_input.ready_dt (and optionally a
    # raw ready_override_str) must be derived from the SAME now() snapshot
    # (e.g. ready_u_zero_full_window, day_rollover_ready_time) rather than
    # resolved independently. When set, overrides start_dt,
    # target_input.ready_dt, and target_input.ready_override_str at run
    # time. Third tuple element is None to leave ready_override_str as
    # whatever target_input already had.
    dynamic_setup: Optional[
        Callable[[DaCalc], tuple[dt.datetime, dt.datetime, Optional[str]]]
    ] = None
    remove_stop_entity_on_target: bool = False
    # Computes (actual_soc, wished_level) for the TARGET ev from its real
    # config at run time, overriding whatever target_input carried. Needed by
    # the minimum-duty cases, which must derive the SoC pair backwards from
    # the car's own top-stage delivery rather than hardcoding percentages —
    # see remainder_soc_factory.
    soc_factory: Optional[Callable[[DaCalc, int], tuple[float, float]]] = None
    # pass criteria
    expect_scheduled: Optional[bool] = None  # None -> don't check
    expect_reason_substr: Optional[str] = None
    expect_ready_index_zero: bool = False
    # When set, also parses and checks the OTHER EV's scheduling outcome —
    # used for the two-EVs-simultaneously case, where both cars have real
    # charging needs rather than the default away/unplugged "other_input".
    other_expect_scheduled: Optional[bool] = None
    # Minimum number of partial-duty intervals the case must produce. Used by
    # the minimum-duty cases as a "does this case still bite?" guard: they are
    # NEGATIVE tests (assert no slivers), so if the engineered remainder ever
    # stops landing partway through an interval, they would silently pass
    # while testing nothing. Note this count is stable across the fix — the
    # remainder interval is partial either way, only its size changes.
    expect_partial_at_least: Optional[int] = None
    # Whether the model's min-duty feasibility guard ("minimale schakelduur
    # ... wordt niet toegepast") is expected to fire. None -> don't check.
    expect_min_duty_guard: Optional[bool] = None
    # Whether day_ahead.py is expected to clip wished_level down for
    # insufficient time ("Er is te weinig tijd..."). None -> don't check.
    # For instant_charge cases this should be explicitly False: instant
    # charge is supposed to ignore entity_ready_datetime entirely, so if
    # this fires despite instant_charge=True, that's Bug 7 (day_ahead.py
    # reads hours_avail from entity_ready_datetime unconditionally, before
    # the instant_charge branch is ever consulted).
    expect_wished_level_clipped: Optional[bool] = None


def _now_plus(hours: float = 0, minutes: float = 0) -> dt.datetime:
    return dt.datetime.now() + dt.timedelta(hours=hours, minutes=minutes)


# ---------------------------------------------------------------------------
# Minimum-duty helpers
# ---------------------------------------------------------------------------


def nominal_min_duty(da_calc: DaCalc) -> float:
    """Lower bound on the true per-interval `min_duty` used by the model.

    day_ahead.py computes min_duty = min(1.0, EV_MIN_DUTY_S / (hr_fraction *
    3600)) per interval. `hr_fraction * 3600` is at most `interval_s` (it is
    SHORTER at u=0, because the solve rarely starts on an interval boundary,
    and at u=ready_u, which runs only until the deadline). A shorter interval
    means a LARGER min_duty, so `EV_MIN_DUTY_S / interval_s` is a floor on
    min_duty across every interval.

    Using the floor makes the sliver check conservative in the right
    direction: it can never produce a false positive, and can only miss a
    violation on the first or last interval — the two intervals whose exact
    hr_fraction the harness cannot reconstruct from the log without
    duplicating day_ahead.py's own interval-alignment arithmetic (the very
    duplication that made earlier versions of case 4.3 timing-fragile).
    """
    interval_s = float(getattr(da_calc, "interval_s", 900))
    return min(1.0, EV_MIN_DUTY_S / interval_s)


def _top_stage_accu_kw(da_calc: DaCalc, ev_index: int) -> float:
    """Accu-side kW of the highest charge stage, mirroring day_ahead.py's
    own derivation (ampere x phases x 230 / 1000 x efficiency)."""
    ev = da_calc.ev_options[ev_index]
    stages = ev.charge_stages
    top = stages[-1]
    ampere = float(getattr(top, "ampere", 0.0))
    efficiency = float(getattr(top, "efficiency", 1.0) or 1.0)
    try:
        ha_getter = lambda eid: da_calc.get_state(eid).state
        three_phase = bool(ev.charge_three_phase.resolve(ha_getter))
    except Exception:  # noqa: BLE001 - config shape varies, see docstring
        three_phase = False
    phases = 3 if three_phase else 1
    return ampere * phases * 230 / 1000 * efficiency


def remainder_soc_factory(
    full_intervals: int,
    remainder_kwh: float,
    base_soc: float = 30.0,
) -> Callable[[DaCalc, int], tuple[float, float]]:
    """Build a (actual_soc, wished_level) factory that engineers a small
    leftover on top of a whole number of full-power intervals.

    The sliver defect only surfaces when the optimizer wants to run N
    intervals at full duty plus a tiny fraction of one more, to land inside
    the +/-0.001 kWh `ev_energy_slack` band. An arbitrary SoC pair produces a
    uniformly-distributed remainder, so it provokes a sliver only rarely.
    This computes the SoC percentages backwards from the car's own top-stage
    delivery so the remainder is deliberately tiny:

        e_needed = full_intervals * (top_stage_accu_kW * interval_hours)
                   + remainder_kwh

    `remainder_kwh` should be comfortably below the smallest amount the fixed
    model can deliver in one switching action (top_stage_accu_kW *
    EV_MIN_DUTY_S / 3600), so that the PRE-fix code has to answer it with a
    sliver and the POST-fix code is forced to redistribute instead.
    """

    def factory(da_calc: DaCalc, ev_index: int) -> tuple[float, float]:
        ev = da_calc.ev_options[ev_index]
        capacity = float(ev.capacity)
        interval_h = float(getattr(da_calc, "interval_s", 900)) / 3600
        per_interval = _top_stage_accu_kw(da_calc, ev_index) * interval_h
        e_needed = full_intervals * per_interval + remainder_kwh
        wished = base_soc + (e_needed / capacity) * 100
        if wished > 100.0:
            raise ValueError(
                f"remainder_soc_factory: full_intervals={full_intervals} needs "
                f"{e_needed:.3f} kWh, which exceeds EV {ev.name}'s capacity "
                f"from {base_soc}% — lower full_intervals or base_soc."
            )
        # 4 decimals: the setup echo logs SoC as a plain float, and the model
        # reads it back as a float, so extra precision is neither lost nor
        # needed.
        return round(base_soc, 4), round(wished, 4)

    return factory


CASES: list[TestCase] = [
    # --- Section 1: core exclusivity (Golf only) ---
    TestCase(
        id="1.1",
        description="Golf blend trap: 30->63%, ready +4h, ~3.00 kW avg",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=4),
        ),
        expect_scheduled=True,
    ),
    TestCase(
        id="1.2",
        description="Golf near 16A ceiling: 30->67%, ready +4h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=67.0, ready_dt=_now_plus(hours=4),
        ),
        expect_scheduled=True,
    ),
    TestCase(
        id="1.3",
        description="Golf below 10A capacity: 30->63%, ready +8h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=8),
        ),
        expect_scheduled=True,
    ),
    TestCase(
        id="1.4",
        description="Golf small job, lots of slack: 30->40%, ready +2h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=40.0, ready_dt=_now_plus(hours=2),
        ),
        expect_scheduled=True,
    ),
    TestCase(
        id="1.5",
        description="Golf above max power: 30->63%, ready +3h20m -> auto-adjusted",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0,
            ready_dt=_now_plus(hours=3, minutes=20),
        ),
        expect_scheduled=True,
    ),
    # --- Section 2: scheduling decision branches ---
    TestCase(
        id="2.1", description="Already at target level",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=80.0,
            instant_charge=False, wished_level=80.0, ready_dt=_now_plus(hours=2),
        ),
        expect_scheduled=False,
        expect_reason_substr="hoger is of gelijk aan",
    ),
    TestCase(
        id="2.2", description="Car away",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="away", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=4),
        ),
        expect_scheduled=False,
        expect_reason_substr="auto is niet huis",
    ),
    TestCase(
        id="2.3", description="Not plugged in",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=False, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=4),
        ),
        expect_scheduled=False,
        expect_reason_substr="auto is niet ingeplugd",
    ),
    TestCase(
        id="2.4", description="Ready time in the past",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0,
            ready_dt=_now_plus(hours=-24),
        ),
        expect_scheduled=False,
        expect_reason_substr="is verouderd",
    ),
    TestCase(
        id="2.5", description="Ready beyond horizon",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0,
            ready_dt=_now_plus(hours=30),
        ),
        expect_scheduled=False,
        expect_reason_substr="ligt voorbij de planningshorizon",
    ),
    TestCase(
        id="2.6", description="Combine away + unplugged + stale ready",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=False, position="away", actual_soc=30.0,
            instant_charge=False, wished_level=63.0,
            ready_dt=_now_plus(hours=-24),
        ),
        expect_scheduled=False,
    ),
    # --- Section 4: partial duty / stage 0, no-stop-entity guard ---
    TestCase(
        id="4.3",
        description="Ready near end of current interval -> ready_u == 0",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=60.0,
            instant_charge=False, wished_level=63.0,
        ),
        dynamic_setup=ready_u_zero_full_window(45),
        expect_scheduled=True,
    ),
    TestCase(
        id="4.4", description="No stop entity, blend-trap case -> interval 0 must be 0/1",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=4),
        ),
        remove_stop_entity_on_target=True,
        expect_scheduled=True,
    ),
    # --- Section 5: instant charge ---
    TestCase(
        id="5.1",
        description="Instant charge on, Golf 30%, generous deadline (baseline)",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0, instant_charge=True, wished_level=100.0,
	    ready_dt=_now_plus(hours=8),
        ),
        expect_scheduled=True,
        expect_wished_level_clipped=False,
    ),
    TestCase(
        id="5.2",
        description=(
            "Bug 7 regression: instant charge on, Golf 30%, but "
            "entity_ready_datetime deliberately short (+15 min). Instant "
            "charge must ignore this deadline entirely — day_ahead.py "
            "reads hours_avail from entity_ready_datetime unconditionally, "
            "before instant_charge is checked, so a tight/stale value "
            "there can silently clip wished_level even though instant "
            "charge is supposed to override it. Golf's max charge rate "
            "(~3.68 kW) over 15 min gives well under 1 kWh 'available', "
            "vs. the ~25.4 kWh a 30%->100% target actually needs, so if "
            "this bug is live the clip fires hard and unambiguously."
        ),
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0, instant_charge=True,
            wished_level=100.0, ready_dt=_now_plus(minutes=15),
        ),
        expect_scheduled=True,
        expect_wished_level_clipped=False,
    ),
    TestCase(
        id="1.6",
        description=(
            "Zero-slack energy_needed infeasibility regression: Golf 30%, "
            "ready +1h50m (clamped to max_possible, per fix prompt's exact repro)"
        ),
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=90.0,
            ready_dt=_now_plus(hours=1, minutes=50),
        ),
        expect_scheduled=True,
    ),
    # --- Section 3: ready-time parsing (short format + day rollover) ---
    TestCase(
        id="3.3",
        description="Day rollover: short HH:MM:SS ready time, earlier than start -> next day",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0,
        ),
        dynamic_setup=day_rollover_ready_time(hour=1, minute=0),
        expect_scheduled=True,
    ),
    # --- Section 6.7: two EVs scheduled simultaneously (regression test for
    # a previously-fixed cross-EV bug) ---
    TestCase(
        id="6.7",
        description="Two EVs simultaneously: Golf 30->63% + Tesla 35->80%, both ready +4h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=30.0,
            instant_charge=False, wished_level=63.0, ready_dt=_now_plus(hours=4),
        ),
        other_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=35.0,
            instant_charge=False, wished_level=80.0, ready_dt=_now_plus(hours=4),
        ),
        expect_scheduled=True,
        other_expect_scheduled=True,
    ),
    # --- Section 1, Tesla control case (should NOT need to blend) ---
    TestCase(
        id="1.T", description="Tesla control: monotone curve, should single-stage trivially",
        target="tesla",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=35.0,
            instant_charge=False, wished_level=80.0, ready_dt=_now_plus(hours=3),
        ),
        expect_scheduled=True,
    ),
    # --- Section 7: minimum duty cycle (EV handover addendum §19, Bug 2) ---
    # These provoke the sub-tolerance duty sliver: the LP giving a REAL stage
    # a weight of ~0.003 (roughly a one-second charge command) purely to land
    # inside the +/-0.001 kWh ev_energy_slack band. Legal before the fix,
    # not dispatchable — a contactor can't usefully close for a second, and
    # the stop time is formatted "%H:%M".
    #
    # Each case engineers energy_needed to be a whole number of full-power
    # intervals plus a remainder far too small to deliver in one 5-minute
    # switching action, so the pre-fix solver has to answer with a sliver and
    # the post-fix solver is forced to redistribute across intervals instead.
    #
    # The assertion itself lives in run_case and applies to every case in
    # this file; Section 7 exists to make sure something actually walks into
    # it. expect_partial_at_least guards against these quietly ceasing to
    # provoke anything.
    TestCase(
        id="7.1",
        description="Golf duty sliver, slack window: 6 full intervals + 0.22 kWh, ready +6h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home",
            instant_charge=False, ready_dt=_now_plus(hours=6),
        ),
        # v4 used 0.02 kWh here. Empirically (min_duty_s=0 run) that let the
        # Golf's non-monotonic curve resolve the remainder via stage
        # substitution instead of a short duty cycle — min factor barely
        # moved between fix-on and fix-off. Raised to 0.22 kWh, still under
        # the Golf's ~0.28 kWh single-switch floor (min stage accu_power *
        # 300s), so substitution remains worse than one short duty cycle.
        soc_factory=remainder_soc_factory(full_intervals=6, remainder_kwh=0.22),
        expect_scheduled=True,
        expect_partial_at_least=1,
    ),
    TestCase(
        id="7.2",
        description="Golf duty sliver, near-saturated window: 10 full intervals + 0.24 kWh, ready +3h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home",
            instant_charge=False, ready_dt=_now_plus(hours=3),
        ),
        # ~10 of ~12 available intervals must be full, so the optimizer has
        # almost no freedom about WHERE to put the remainder — a different
        # branch from 7.1, where it can shop for the cheapest interval.
        # v4's 0.04 kWh remainder produced a 0.9998 min factor (essentially
        # full, no sliver even with min_duty_s=0) — same substitution
        # failure mode as 7.1, raised for the same reason.
        soc_factory=remainder_soc_factory(full_intervals=10, remainder_kwh=0.24),
        expect_scheduled=True,
        expect_partial_at_least=1,
    ),
    TestCase(
        id="7.3",
        description="Tesla duty sliver (monotone curve control): 6 full intervals + 0.02 kWh, ready +5h",
        target="tesla",
        target_input=EvCaseInput(
            plugged_in=True, position="home",
            instant_charge=False, ready_dt=_now_plus(hours=5),
        ),
        # The Tesla's curve is monotone, so unlike the Golf there is never a
        # cost reason to blend stages. If a sliver shows up HERE it is purely
        # the energy-band remainder, with the non-monotonic-curve explanation
        # ruled out.
        soc_factory=remainder_soc_factory(full_intervals=6, remainder_kwh=0.02, base_soc=35.0),
        expect_scheduled=True,
        expect_partial_at_least=1,
    ),
    TestCase(
        id="7.4",
        description="Golf duty sliver with no stop entity: 4 full intervals + 0.20 kWh, ready +4h",
        target="golf",
        target_input=EvCaseInput(
            plugged_in=True, position="home",
            instant_charge=False, ready_dt=_now_plus(hours=4),
        ),
        # v4's 0.02 kWh remainder was absorbed by substitution (min factor
        # 0.3949 with min_duty_s=0 — barely below the bound, not the clear
        # sliver 7.3/7.5 showed). Raised for the same reason as 7.1/7.2.
        soc_factory=remainder_soc_factory(full_intervals=4, remainder_kwh=0.20),
        # Without entity_stop_charging, day_ahead.py already forces interval 0
        # to be fully on or fully off. This checks the two mechanisms compose:
        # interval 0 all-or-nothing AND every other interval respecting the
        # minimum duty, with the model still feasible.
        remove_stop_entity_on_target=True,
        expect_scheduled=True,
        expect_partial_at_least=1,
    ),
    TestCase(
        id="7.5",
        description="Tesla small top-up near the min-duty feasibility guard: 60->61.2%",
        target="tesla",
        target_input=EvCaseInput(
            plugged_in=True, position="home", actual_soc=60.0,
            instant_charge=False, wished_level=61.2, ready_dt=_now_plus(hours=2),
        ),
        # ~0.66 kWh total. Whether this trips day_ahead.py's guard (skip the
        # minimum-duty constraint when energy_needed is below one switching
        # action) depends on this car's top-stage power: at 3-phase 16A one
        # 5-minute action already delivers ~0.92 kWh, so the guard fires; at
        # 1-phase it delivers ~0.28 kWh and it does not. Deliberately left
        # unasserted — read `min_duty_guard_fired` in the report, then pin
        # expect_min_duty_guard to whatever your config actually does, so a
        # later config change that moves this boundary is caught.
        #
        # expect_scheduled is also left unchecked: if level_margin exceeds
        # the requested delta, day_ahead.py correctly declines to schedule at
        # all, and that is not this case's concern. What IS asserted is that
        # the solve stays feasible and produces no slivers.
        expect_min_duty_guard=None,
    ),
]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

PAIR_RE = re.compile(r"(-?[\d.]+)\((-?[\d.]+)\)")
ROW_RE = re.compile(r"^(\d{2}:\d{2})\s{2}(.*)$")

_ECHO_INSTANT_RE = re.compile(r"Direct laden is (aan|uit)")
_ECHO_READY_RE = re.compile(r"Klaar met laden op: (\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")
_ECHO_ACTUAL_RE = re.compile(r"Huidig laadniveau: ([\d.]+) %")
_ECHO_WISHED_RE = re.compile(r"Gewenst laadniveau:([\d.]+) %")
_ECHO_POSITION_RE = re.compile(r"Locatie: (\S+)")
_ECHO_PLUGGED_RE = re.compile(r"Ingeplugged:(True|False)")
_ECHO_CAPACITY_RE = re.compile(r"Capaciteit accu: ([\d.]+) kWh")

# Known capacities of the two mocked test cars — used as a cheap sanity
# check that each EV's own log block shows ITS OWN config, not the other
# car's (the exact class of bug the "two EVs simultaneously" fix addressed:
# per-EV loop state leaking across cars). Update if the mocked configs
# change.
EV_CAPACITY_KWH = {"tesla": 55.0, "golf": 36.3}


@dataclass
class SetupEcho:
    instant_charge: Optional[bool] = None
    ready_dt: Optional[dt.datetime] = None
    actual_soc: Optional[float] = None
    wished_level: Optional[float] = None
    position: Optional[str] = None
    plugged_in: Optional[bool] = None
    capacity_kwh: Optional[float] = None


def parse_setup_echo(block_lines: list[str]) -> SetupEcho:
    echo = SetupEcho()
    for line in block_lines:
        m = _ECHO_INSTANT_RE.search(line)
        if m:
            echo.instant_charge = m.group(1) == "aan"
        m = _ECHO_READY_RE.search(line)
        if m:
            echo.ready_dt = dt.datetime.strptime(m.group(1), "%d-%m-%Y %H:%M:%S")
        m = _ECHO_ACTUAL_RE.search(line)
        if m:
            echo.actual_soc = float(m.group(1))
        m = _ECHO_WISHED_RE.search(line)
        if m:
            echo.wished_level = float(m.group(1))
        m = _ECHO_POSITION_RE.search(line)
        if m:
            echo.position = m.group(1)
        m = _ECHO_PLUGGED_RE.search(line)
        if m:
            echo.plugged_in = m.group(1) == "True"
        m = _ECHO_CAPACITY_RE.search(line)
        if m:
            echo.capacity_kwh = float(m.group(1))
    return echo


def check_capacity(car_key: str, echo: SetupEcho) -> Optional[str]:
    """Cheap cross-EV-leak sanity check: does this car's log block show
    ITS OWN known capacity? A mismatch would mean the wrong EV's config
    got read into this block — exactly the class of bug the "two EVs
    simultaneously" PR fixed — so it's checked for both EVs on every case,
    not just the dedicated two-EV case."""
    expected = EV_CAPACITY_KWH.get(car_key)
    if expected is None or echo.capacity_kwh is None:
        return None
    if abs(expected - echo.capacity_kwh) > 0.05:
        return (
            f"capacity sanity check ({car_key}): expected {expected} kWh, "
            f"log shows {echo.capacity_kwh} kWh — possible EV index mix-up "
            f"or cross-EV variable leak"
        )
    return None


def verify_setup_echo(resolved: ResolvedEvInput, echo: SetupEcho) -> list[str]:
    """Compare what we asked for against what the log says actually got
    read. Only checks fields we explicitly set. A mismatch here means an
    override silently didn't take effect (usually: the entity_id it should
    have targeted is None/unconfigured for this EV) — see case 5.1."""
    mismatches = []
    if resolved.plugged_in is not None and echo.plugged_in is not None:
        if resolved.plugged_in != echo.plugged_in:
            mismatches.append(
                f"plugged_in: requested {resolved.plugged_in}, log shows {echo.plugged_in}"
            )
    if resolved.position is not None and echo.position is not None:
        if resolved.position.lower() != echo.position.lower():
            mismatches.append(
                f"position: requested {resolved.position!r}, log shows {echo.position!r}"
            )
    if resolved.actual_soc is not None and echo.actual_soc is not None:
        if abs(resolved.actual_soc - echo.actual_soc) > 0.05:
            mismatches.append(
                f"actual_soc: requested {resolved.actual_soc}, log shows {echo.actual_soc}"
            )
    if resolved.instant_charge is not None and echo.instant_charge is not None:
        if resolved.instant_charge != echo.instant_charge:
            mismatches.append(
                f"instant_charge: requested {resolved.instant_charge}, log shows "
                f"{echo.instant_charge} (entity_instant_start is likely None/"
                f"unconfigured for this EV — override had nothing to write to)"
            )
    if resolved.wished_level is not None and echo.wished_level is not None:
        if abs(resolved.wished_level - echo.wished_level) > 0.05:
            mismatches.append(
                f"wished_level: requested {resolved.wished_level}, log shows "
                f"{echo.wished_level}"
            )
    if resolved.ready_dt is not None and echo.ready_dt is not None:
        delta = abs((resolved.ready_dt - echo.ready_dt).total_seconds())
        if delta > 5:
            mismatches.append(
                f"ready_dt: requested {resolved.ready_dt}, log shows {echo.ready_dt} "
                f"({delta:.0f}s off)"
            )
    return mismatches


@dataclass
class SolveStats:
    wall_time_sec: Optional[float] = None
    nodes: Optional[int] = None
    gap: Optional[float] = None
    objective: Optional[float] = None
    cost_after_optimize: Optional[float] = None
    # Whether the model actually reached an optimal solution. calc_optimum()
    # returns None immediately on model.num_solutions == 0 (infeasible), or
    # if self.strategy doesn't match a known value — BEFORE any EV dispatch
    # logging (the per-interval factor table, partial/boundary/start-stop
    # counts) ever runs. That means `scheduled` (parsed from the setup
    # block, printed before model.optimize()) can still read True, and
    # multi_stage_intervals is simply empty because there was no table to
    # search — a fully infeasible solve would otherwise sail through this
    # harness as a false PASS. Fail-closed: solved is only True if the
    # exact success line is found, not merely "no failure line found".
    solved: bool = False
    failure_reason: Optional[str] = None


_STATS_TIME_RE = re.compile(r"Rekentijd:\s*([\d.]+)\s*sec")
_STATS_NODES_RE = re.compile(r"took \d+ iterations and (\d+) nodes")
_STATS_GAP_RE = re.compile(r"Exiting as integer gap of ([\-\d.eE]+) less than")
_STATS_OBJ_RE = re.compile(r"Search completed - best objective ([\-\d.eE]+),")
_STATS_COST_RE = re.compile(r"Cost after optimize\s+([\-\d.]+)")
_STATS_SUCCESS_RE = re.compile(
    r"Het programma heeft een optimale oplossing gevonden\."
)
_STATS_FAILURE_RE = re.compile(
    r"(Geen oplossing(?: in na herberekening)? voor: [^\n]*"
    r"|Kies een strategie in options"
    r"|Er is helaas geen oplossing gevonden[^\n]*)"
)


def parse_solve_stats(log_text: str) -> SolveStats:
    stats = SolveStats()
    m = _STATS_TIME_RE.search(log_text)
    if m:
        stats.wall_time_sec = float(m.group(1))
    m = _STATS_NODES_RE.search(log_text)
    if m:
        stats.nodes = int(m.group(1))
    m = _STATS_GAP_RE.search(log_text)
    if m:
        stats.gap = float(m.group(1))
    m = _STATS_OBJ_RE.search(log_text)
    if m:
        stats.objective = float(m.group(1))
    m = _STATS_COST_RE.search(log_text)
    if m:
        stats.cost_after_optimize = float(m.group(1))
    stats.solved = bool(_STATS_SUCCESS_RE.search(log_text))
    m = _STATS_FAILURE_RE.search(log_text)
    if m:
        stats.failure_reason = m.group(1)
    return stats


@dataclass
class ParsedEvRun:
    scheduled: Optional[bool] = None
    reason: Optional[str] = None
    energy_needed_kwh: Optional[float] = None
    rows: list[dict] = field(default_factory=list)  # per-interval parsed data
    partial_stops: Optional[int] = None
    boundary_stops: Optional[int] = None
    start_stops: Optional[int] = None
    multi_stage_intervals: list[str] = field(default_factory=list)  # 'uur' values
    # (uur, stage_index, factor) for every real stage running below the
    # minimum duty cycle but above zero — i.e. a charge command too short to
    # dispatch. Empty list is the passing state.
    duty_slivers: list[tuple[str, int, float]] = field(default_factory=list)
    # Smallest non-zero real-stage factor seen anywhere in the run. Reported
    # rather than asserted: it is the number a human reads to judge whether a
    # minimum-duty case is still provoking anything.
    min_nonzero_factor: Optional[float] = None
    # True iff day_ahead.py logged that it skipped the minimum-duty
    # constraint because energy_needed was below one switching action.
    min_duty_guard_fired: bool = False
    # True iff day_ahead.py logged "Er is te weinig tijd" and clamped
    # wished_level down for insufficient time before the deadline. For an
    # instant_charge case this must never fire — instant charge is supposed
    # to target the full wished level regardless of whatever
    # entity_ready_datetime happens to hold. If it fires on an
    # instant_charge case, that's Bug 7.
    wished_level_clipped: bool = False
    setup_echo: SetupEcho = field(default_factory=SetupEcho)


def parse_ev_log(log_text: str, ev_name: str, min_duty: float = 0.0) -> ParsedEvRun:
    result = ParsedEvRun()
    lines = log_text.splitlines()

    # setup block: "Instellingen voor laden van EV: {name}" ... next such
    # line or end
    setup_start = None
    for i, line in enumerate(lines):
        if line.startswith(f"Instellingen voor laden van EV: {ev_name}"):
            setup_start = i
            break
    if setup_start is not None:
        setup_end = len(lines)
        for j in range(setup_start + 1, len(lines)):
            if lines[j].startswith("Instellingen voor laden van EV:"):
                setup_end = j
                break
        block = lines[setup_start:setup_end]
        result.setup_echo = parse_setup_echo(block)
        for line in block:
            m = re.search(r"Benodigde netto energie: ([\d.]+) kWh", line)
            if m:
                result.energy_needed_kwh = float(m.group(1))
            if "Er is te weinig tijd" in line:
                result.wished_level_clipped = True
            if "Opladen wordt niet ingepland, omdat" in line:
                result.scheduled = False
                result.reason = line.split("omdat", 1)[1].strip()
            elif "Opladen wordt ingepland." in line:
                result.scheduled = True

    # factor table: "Inzet-factor laden {name} per stop" ... rows ... until
    # a non-row line
    for i, line in enumerate(lines):
        if line == f"Inzet-factor laden {ev_name} per stop":
            j = i + 2  # skip this line + header line
            while j < len(lines):
                m = ROW_RE.match(lines[j])
                if not m:
                    break
                uur, rest = m.group(1), m.group(2)
                try:
                    pairs = PAIR_RE.findall(rest)
                    remainder = PAIR_RE.sub("", rest)
                    nums = [float(x) for x in remainder.split()]
                    row = {
                        "uur": uur,
                        "stage_factors": [float(p[0]) for p in pairs],
                        "stage_on": [float(p[1]) for p in pairs],
                    }
                    if len(nums) >= 9:
                        (row["cons"], row["power"], row["on"], row["off"],
                         row["part"], row["bound"], row["soc"], row["delta"],
                         row["cost"]) = nums[:9]
                    result.rows.append(row)
                    real_active = [
                        k for k, f in enumerate(row["stage_factors"])
                        if k >= 1 and f > 1e-6
                    ]
                    if len(real_active) > 1:
                        result.multi_stage_intervals.append(uur)
                    # Minimum duty cycle: a real stage is either off or runs
                    # for at least min_duty of the interval. Stage 0 is
                    # deliberately exempt — its weight absorbs the idle
                    # remainder, which is what makes partial duty possible at
                    # all.
                    for k, f in enumerate(row["stage_factors"]):
                        if k < 1 or f <= DUTY_ZERO_TOL:
                            continue
                        if (result.min_nonzero_factor is None
                                or f < result.min_nonzero_factor):
                            result.min_nonzero_factor = f
                        if min_duty > 0 and f < min_duty - DUTY_COMPARE_TOL:
                            result.duty_slivers.append((uur, k, f))
                except ValueError as ex:
                    logging.warning(
                        f"parse_ev_log: could not parse row {uur!r}: "
                        f"{ex} — raw line: {lines[j]!r}"
                    )
                j += 1
            break

    # min-duty feasibility guard. Logged from the model-building loop, which
    # runs after ALL the setup echo blocks, so this is scoped by EV name
    # rather than by position in the log.
    for line in lines:
        if (f"EV {ev_name}:" in line
                and "minimale schakelduur" in line
                and "niet toegepast" in line):
            result.min_duty_guard_fired = True
            break

    # summary lines, scoped after "wordt geladen tussen" / "is niet
    # ingepland" for this ev, before the next ev's such line
    anchor_idx = None
    for i, line in enumerate(lines):
        if (line.startswith(f"{ev_name} wordt geladen tussen")
                or line == f"Laden van {ev_name} is niet ingepland"):
            anchor_idx = i
            break
    if anchor_idx is not None:
        for line in lines[anchor_idx:anchor_idx + 6]:
            m = re.search(r"Aantal partial stops:\s*([\d.]+)", line)
            if m:
                result.partial_stops = int(float(m.group(1)))
            m = re.search(r"Aantal boundary stops:\s*([\d.]+)", line)
            if m:
                result.boundary_stops = int(float(m.group(1)))
            m = re.search(r"Aantal start/stops:\s*([\d.]+)", line)
            if m:
                result.start_stops = int(float(m.group(1)))

    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def build_overrides(da_calc: DaCalc, ev_index: int, resolved: ResolvedEvInput) -> dict:
    ev = da_calc.ev_options[ev_index]
    overrides = {}
    if resolved.plugged_in is not None:
        overrides[ev.entity_plugged_in] = "on" if resolved.plugged_in else "off"
    if resolved.position is not None:
        overrides[ev.entity_position] = resolved.position
    if resolved.actual_soc is not None:
        overrides[ev.entity_actual_level] = resolved.actual_soc
    if resolved.instant_charge is not None and ev.entity_instant_start is not None:
        overrides[ev.entity_instant_start] = "on" if resolved.instant_charge else "off"
    if resolved.wished_level is not None:
        if resolved.instant_charge and ev.entity_instant_level is not None:
            overrides[ev.entity_instant_level] = resolved.wished_level
        elif ev.charge_scheduler is not None:
            overrides[ev.charge_scheduler.entity_set_level] = resolved.wished_level
    if resolved.ready_override_str is not None and ev.charge_scheduler is not None:
        overrides[ev.charge_scheduler.entity_ready_datetime] = resolved.ready_override_str
    elif resolved.ready_dt is not None and ev.charge_scheduler is not None:
        overrides[ev.charge_scheduler.entity_ready_datetime] = (
            resolved.ready_dt.strftime("%Y-%m-%d %H:%M:%S")
        )
    return overrides


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_MISMATCH = "SETUP_MISMATCH"
STATUS_ERROR = "ERROR"
STATUS_INFEASIBLE = "INFEASIBLE"


@dataclass
class CaseResult:
    id: str
    description: str
    status: str
    failures: list[str]
    mismatches: list[str]
    parsed: ParsedEvRun
    stats: SolveStats


def run_case(da_calc: DaCalc, case: TestCase, ev_index_tesla: int,
             ev_index_golf: int) -> CaseResult:
    target_index = ev_index_tesla if case.target == "tesla" else ev_index_golf
    other_index = ev_index_golf if case.target == "tesla" else ev_index_tesla
    target_name = da_calc.ev_options[target_index].name
    other_name = da_calc.ev_options[other_index].name
    other_key = "golf" if case.target == "tesla" else "tesla"

    resolved_target = _resolve(da_calc, case.target_input)
    resolved_other = _resolve(da_calc, case.other_input)

    if case.soc_factory is not None:
        # Derived from the target's real config, so it must run before
        # build_overrides AND before verify_setup_echo reads resolved_target
        # — the echo check is what catches a factory that silently computed
        # something the model then didn't use.
        resolved_target.actual_soc, resolved_target.wished_level = (
            case.soc_factory(da_calc, target_index)
        )

    effective_start_dt = case.start_dt
    if case.dynamic_setup is not None:
        dyn_start, dyn_ready, dyn_ready_override = case.dynamic_setup(da_calc)
        effective_start_dt = dyn_start
        resolved_target.ready_dt = dyn_ready
        if dyn_ready_override is not None:
            resolved_target.ready_override_str = dyn_ready_override

    overrides = {}
    overrides.update(build_overrides(da_calc, target_index, resolved_target))
    overrides.update(build_overrides(da_calc, other_index, resolved_other))

    stop_entity_ctx = (
        _with_stop_entity_removed(da_calc, target_index)
        if case.remove_stop_entity_on_target
        else _null_ctx()
    )

    with (stop_entity_ctx, get_state_overrides(da_calc, overrides),
          capture_log() as buf, capture_native_stdout() as native):
        try:
            da_calc.debug = True  # see module docstring: not optional
            da_calc.calc_optimum(_start_dt=effective_start_dt)
        except Exception as ex:
            log_text = buf.getvalue()
            stats_text = log_text + "\n" + native["text"]
            return CaseResult(
                id=case.id, description=case.description, status=STATUS_ERROR,
                failures=[f"EXCEPTION during solve: {ex!r}"], mismatches=[],
                parsed=ParsedEvRun(), stats=parse_solve_stats(stats_text),
            )

    log_text = buf.getvalue()
    native_text = native["text"]
    min_duty = nominal_min_duty(da_calc)
    parsed = parse_ev_log(log_text, target_name, min_duty)
    parsed_other = parse_ev_log(log_text, other_name, min_duty)
    stats = parse_solve_stats(log_text + "\n" + native_text)

    if not stats.solved:
        return CaseResult(
            id=case.id, description=case.description, status=STATUS_INFEASIBLE,
            failures=[
                f"model did not reach an optimal solution "
                f"({stats.failure_reason or 'no success line found in log'}) "
                f"— calc_optimum() returns None before any EV dispatch "
                f"logging runs, so 'scheduled' and multi-stage checks below "
                f"would be misleadingly clean; this is checked first"
            ],
            mismatches=[], parsed=parsed, stats=stats,
        )

    mismatches = verify_setup_echo(resolved_target, parsed.setup_echo)
    for note in (
        check_capacity(case.target, parsed.setup_echo),
        check_capacity(other_key, parsed_other.setup_echo),
    ):
        if note is not None:
            mismatches.append(note)

    if mismatches:
        return CaseResult(
            id=case.id, description=case.description, status=STATUS_MISMATCH,
            failures=[], mismatches=mismatches, parsed=parsed, stats=stats,
        )

    failures: list[str] = []
    if case.expect_scheduled is not None and parsed.scheduled != case.expect_scheduled:
        failures.append(
            f"expected scheduled={case.expect_scheduled}, got {parsed.scheduled}"
        )
    if case.expect_reason_substr and (
        not parsed.reason or case.expect_reason_substr not in parsed.reason
    ):
        failures.append(
            f"expected reason containing {case.expect_reason_substr!r}, "
            f"got {parsed.reason!r}"
        )
    if parsed.multi_stage_intervals:
        failures.append(
            f"MULTIPLE REAL STAGES ACTIVE at: {parsed.multi_stage_intervals}"
        )
    # Other EV is checked on every case (cheap, and it's exactly the class
    # of leak the two-EV-simultaneous fix addressed), not just when it's
    # the deliberate focus of the case.
    if parsed_other.multi_stage_intervals:
        failures.append(
            f"OTHER EV ({other_name}) MULTIPLE REAL STAGES ACTIVE at: "
            f"{parsed_other.multi_stage_intervals}"
        )
    if (case.other_expect_scheduled is not None
            and parsed_other.scheduled != case.other_expect_scheduled):
        failures.append(
            f"other EV ({other_name}): expected scheduled="
            f"{case.other_expect_scheduled}, got {parsed_other.scheduled}"
        )
    # Minimum duty cycle — checked on EVERY case and on BOTH cars, same
    # rationale as the multi-stage check above: it is cheap, and a sliver is
    # not dispatchable regardless of which case happened to produce it.
    for who, p in ((target_name, parsed), (f"OTHER EV ({other_name})", parsed_other)):
        if p.duty_slivers:
            detail = ", ".join(
                f"{uur} stage {k} factor {f:.4f}" for uur, k, f in p.duty_slivers
            )
            failures.append(
                f"{who}: DUTY SLIVER below minimum duty {min_duty:.4f} "
                f"({EV_MIN_DUTY_S:.0f}s) at: {detail}"
            )
    if case.expect_partial_at_least is not None:
        got = parsed.partial_stops
        if got is None or got < case.expect_partial_at_least:
            failures.append(
                f"case no longer provokes partial duty: expected at least "
                f"{case.expect_partial_at_least} partial interval(s), got "
                f"{got}. This is a NEGATIVE test (asserts no slivers), so "
                f"without a partial interval it passes while testing "
                f"nothing — retune the engineered remainder rather than "
                f"relaxing this bound."
            )
    if (case.expect_min_duty_guard is not None
            and parsed.min_duty_guard_fired != case.expect_min_duty_guard):
        failures.append(
            f"expected min-duty feasibility guard fired="
            f"{case.expect_min_duty_guard}, got {parsed.min_duty_guard_fired}"
        )
    if (case.expect_wished_level_clipped is not None
            and parsed.wished_level_clipped != case.expect_wished_level_clipped):
        failures.append(
            f"wished_level_clipped: expected "
            f"{case.expect_wished_level_clipped}, got "
            f"{parsed.wished_level_clipped}"
        )

    status = STATUS_FAIL if failures else STATUS_PASS
    return CaseResult(
        id=case.id, description=case.description, status=status,
        failures=failures, mismatches=[], parsed=parsed, stats=stats,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_reports(results: list[CaseResult], out_dir: Path = REPORT_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"ev_test_report_{timestamp}.md"
    csv_path = out_dir / f"ev_test_report_{timestamp}.csv"
    md_latest = out_dir / "ev_test_report_latest.md"
    csv_latest = out_dir / "ev_test_report_latest.csv"

    counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_MISMATCH: 0,
              STATUS_ERROR: 0, STATUS_INFEASIBLE: 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    # --- Markdown ---
    lines = []
    lines.append(f"# EV charging test report — {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(
        f"**{counts[STATUS_PASS]} passed, {counts[STATUS_FAIL]} failed, "
        f"{counts[STATUS_MISMATCH]} setup mismatch, {counts[STATUS_ERROR]} error, "
        f"{counts[STATUS_INFEASIBLE]} infeasible** "
        f"out of {len(results)} cases."
    )
    lines.append("")
    lines.append(
        "| ID | Status | Description | Scheduled | Energy needed (kWh) | "
        "Partial/Boundary/Start-stops | Min factor | Solve (s / nodes / gap) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        sched = "—" if r.parsed.scheduled is None else str(r.parsed.scheduled)
        energy = "—" if r.parsed.energy_needed_kwh is None else f"{r.parsed.energy_needed_kwh:.3f}"
        psb = f"{r.parsed.partial_stops}/{r.parsed.boundary_stops}/{r.parsed.start_stops}"
        solve = (
            f"{r.stats.wall_time_sec or '—'} / {r.stats.nodes or '—'} / "
            f"{r.stats.gap if r.stats.gap is not None else '—'}"
        )
        minf = (
            "—" if r.parsed.min_nonzero_factor is None
            else f"{r.parsed.min_nonzero_factor:.4f}"
        )
        lines.append(
            f"| {r.id} | {r.status} | {r.description} | {sched} | {energy} | "
            f"{psb} | {minf} | {solve} |"
        )
    lines.append("")

    detail_needed = [r for r in results if r.status != STATUS_PASS]
    if detail_needed:
        lines.append("## Details for non-passing cases")
        lines.append("")
        for r in detail_needed:
            lines.append(f"### {r.id} — {r.description} ({r.status})")
            if r.mismatches:
                lines.append("Setup-echo mismatches (override likely didn't take effect):")
                for m in r.mismatches:
                    lines.append(f"- {m}")
            if r.failures:
                lines.append("Assertion failures:")
                for f in r.failures:
                    lines.append(f"- {f}")
            if r.parsed.reason:
                lines.append(f"\nModel's stated reason: `{r.parsed.reason}`")
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    md_latest.write_text("\n".join(lines), encoding="utf-8")

    # --- CSV ---
    fieldnames = [
        "id", "status", "description", "scheduled", "reason",
        "energy_needed_kwh", "partial_stops", "boundary_stops", "start_stops",
        "multi_stage_intervals", "duty_slivers", "min_nonzero_factor",
        "min_duty_guard_fired", "wished_level_clipped", "failures", "mismatches",
        "wall_time_sec", "nodes", "gap", "objective", "cost_after_optimize",
    ]
    rows = []
    for r in results:
        rows.append({
            "id": r.id,
            "status": r.status,
            "description": r.description,
            "scheduled": r.parsed.scheduled,
            "reason": r.parsed.reason or "",
            "energy_needed_kwh": r.parsed.energy_needed_kwh,
            "partial_stops": r.parsed.partial_stops,
            "boundary_stops": r.parsed.boundary_stops,
            "start_stops": r.parsed.start_stops,
            "multi_stage_intervals": ";".join(r.parsed.multi_stage_intervals),
            "duty_slivers": ";".join(
                f"{uur}/s{k}/{f:.4f}" for uur, k, f in r.parsed.duty_slivers
            ),
            "min_nonzero_factor": r.parsed.min_nonzero_factor,
            "min_duty_guard_fired": r.parsed.min_duty_guard_fired,
            "wished_level_clipped": r.parsed.wished_level_clipped,
            "failures": " | ".join(r.failures),
            "mismatches": " | ".join(r.mismatches),
            "wall_time_sec": r.stats.wall_time_sec,
            "nodes": r.stats.nodes,
            "gap": r.stats.gap,
            "objective": r.stats.objective,
            "cost_after_optimize": r.stats.cost_after_optimize,
        })
    for path in (csv_path, csv_latest):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return md_path, csv_path


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    da_calc = DaCalc(CONFIG_PATH)
    if da_calc.config is None:
        print("Config failed to load — aborting.")
        return

    ev_index_tesla = _find_ev_index(da_calc, "Tesla")
    ev_index_golf = _find_ev_index(da_calc, "Golf")

    results: list[CaseResult] = []
    for case in CASES:
        r = run_case(da_calc, case, ev_index_tesla, ev_index_golf)
        results.append(r)
        print(f"[{r.status}] {r.id}: {r.description}")
        if r.mismatches:
            for m in r.mismatches:
                print(f"        - MISMATCH: {m}")
        if r.failures:
            for f in r.failures:
                print(f"        - {f}")
        if r.parsed.energy_needed_kwh is not None:
            print(f"        energy_needed={r.parsed.energy_needed_kwh:.3f} kWh, "
                  f"partial_stops={r.parsed.partial_stops}, "
                  f"boundary_stops={r.parsed.boundary_stops}, "
                  f"start_stops={r.parsed.start_stops}")

    n_pass = sum(1 for r in results if r.status == STATUS_PASS)
    print(f"\n{n_pass}/{len(results)} passed.")
    non_pass = [r.id for r in results if r.status != STATUS_PASS]
    if non_pass:
        print("Cases needing a look:", non_pass)

    md_path, csv_path = write_reports(results)
    print(f"\nReport written to:\n  {md_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
