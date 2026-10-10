"""Log parsers ported from test_ev_harness_v6.py: read the same Dutch log
lines day_ahead.py's EV dispatch block already produces (the setup echo,
the "Inzet-factor laden ... per stop" table, the summary lines, and CBC's
own solve-stats lines) and turn them into structured per-run data. Pure
text parsing, with no DaCalc dependency, so these work identically
whether the log came from a live run or, as here, a synthetic ReplayIO
solve.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .vocabulary import INTERVAL_S

# --- minimum duty cycle (day_ahead.py's ev_min_duty_s) ----------------------
# Every REAL charge stage (cs >= 1) is constrained to be either off or on for
# at least EV_MIN_DUTY_S seconds via
#     stage_factor[e][cs][u] >= min_duty * stage_on[e][cs][u]
# with min_duty = min(1.0, EV_MIN_DUTY_S / (hr_fraction * 3600)). Keep this in
# sync with day_ahead.py's own constant.
EV_MIN_DUTY_S = 300.0

# Tolerance below which a stage_factor is treated as "off" rather than as a
# sliver (the factor table logs to 4 decimals).
DUTY_ZERO_TOL = 1e-4

# Slack when comparing a factor against min_duty: the log rounds to 4
# decimals (a legal 1/3 prints as "0.3333", 3.3e-5 below min_duty) and CBC
# satisfies constraints only to its own feasibility tolerance.
DUTY_COMPARE_TOL = 1e-4

# A floor on the true per-interval min_duty: EV_MIN_DUTY_S / interval_s.
# Every scenario in this corpus solves on the fixed 15-minute model grid, so
# (unlike the live-clock v6 harness, which had to derive this per DaCalc)
# this is just a constant.
NOMINAL_MIN_DUTY = min(1.0, EV_MIN_DUTY_S / INTERVAL_S)


@dataclass
class SetupEcho:
    instant_charge: Optional[bool] = None
    ready_dt: Optional[dt.datetime] = None
    actual_soc: Optional[float] = None
    wished_level: Optional[float] = None
    position: Optional[str] = None
    plugged_in: Optional[bool] = None
    capacity_kwh: Optional[float] = None


_ECHO_INSTANT_RE = re.compile(r"Direct laden is (aan|uit)")
_ECHO_READY_RE = re.compile(r"Klaar met laden op: (\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")
_ECHO_ACTUAL_RE = re.compile(r"Huidig laadniveau: ([\d.]+) %")
_ECHO_WISHED_RE = re.compile(r"Gewenst laadniveau:([\d.]+) %")
_ECHO_POSITION_RE = re.compile(r"Locatie: (\S+)")
_ECHO_PLUGGED_RE = re.compile(r"Ingeplugged:(True|False)")
_ECHO_CAPACITY_RE = re.compile(r"Capaciteit accu: ([\d.]+) kWh")


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


def check_capacity(expected_kwh: Optional[float], echo: SetupEcho, *, label: str) -> Optional[str]:
    """Cheap cross-EV-leak sanity check: does this car's log block show its
    own configured capacity? A mismatch means the wrong EV's config got
    read into this block. Unlike the v6 original, a hardcoded
    {"tesla": 55.0, "golf": 36.3} table, expected_kwh is read from this
    environment's own config, so it stays correct if the corpus config
    ever changes."""
    if expected_kwh is None or echo.capacity_kwh is None:
        return None
    if abs(expected_kwh - echo.capacity_kwh) > 0.05:
        return (
            f"capacity sanity check ({label}): expected {expected_kwh} kWh, "
            f"log shows {echo.capacity_kwh} kWh — possible EV index mix-up "
            f"or cross-EV variable leak"
        )
    return None


def verify_setup_echo(resolved, echo: SetupEcho) -> list[str]:
    """Compare what was asked for (an ev.ResolvedEvInput) against what the
    log says actually got read. Only checks fields that were explicitly
    set. A mismatch means an override silently didn't take effect, usually
    because the entity_id it should have targeted is None or unconfigured
    for this EV; see case 5.1."""
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
    solved: bool = False
    failure_reason: Optional[str] = None


_STATS_TIME_RE = re.compile(r"Rekentijd:\s*([\d.]+)\s*sec")
_STATS_NODES_RE = re.compile(r"took \d+ iterations and (\d+) nodes")
_STATS_GAP_RE = re.compile(r"Exiting as integer gap of ([\-\d.eE]+) less than")
_STATS_OBJ_RE = re.compile(r"Search completed - best objective ([\-\d.eE]+),")
_STATS_COST_RE = re.compile(r"Cost after optimize\s+([\-\d.]+)")
_STATS_SUCCESS_RE = re.compile(r"Het programma heeft een optimale oplossing gevonden\.")
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
    rows: list[dict] = field(default_factory=list)
    partial_stops: Optional[int] = None
    boundary_stops: Optional[int] = None
    start_stops: Optional[int] = None
    multi_stage_intervals: list[str] = field(default_factory=list)
    # (uur, stage_index, factor) for every real stage running below the
    # minimum duty cycle but above zero. Empty list is the passing state.
    duty_slivers: list[tuple[str, int, float]] = field(default_factory=list)
    min_nonzero_factor: Optional[float] = None
    min_duty_guard_fired: bool = False
    wished_level_clipped: bool = False
    setup_echo: SetupEcho = field(default_factory=SetupEcho)


PAIR_RE = re.compile(r"(-?[\d.]+)\((-?[\d.]+)\)")
ROW_RE = re.compile(r"^(\d{2}:\d{2})\s{2}(.*)$")


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
                    # deliberately exempt: its weight absorbs the idle
                    # remainder, which is what makes partial duty possible.
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

    # min-duty feasibility guard, scoped by EV name (logged from the
    # model-building loop, which runs after all the setup echo blocks).
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
