"""Tier C: per-scenario objective-value baselines.

One ``<scenario_id>.json`` per scenario in ``scenarios/baselines/``, written
**only** by ``python -m dao.prog.da_debug scenario-bless``, never by a plain
``scenario-run``. A scenario with no baseline reports Tier C as ``PENDING``
(not a failure) so first-time setup isn't all-red; a scenario whose baseline
exists reports PASS/FAIL against it, with old/new/delta in the detail.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import BASELINES_DIR

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_PENDING = "PENDING"


def baseline_path(scenario_id: str, baselines_dir: Path | None = None) -> Path:
    return (baselines_dir or BASELINES_DIR) / f"{scenario_id}.json"


def load_baseline(scenario_id: str, baselines_dir: Path | None = None) -> dict | None:
    p = baseline_path(scenario_id, baselines_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def write_baseline(scenario_id: str, objective: float, *, baselines_dir: Path | None = None) -> Path:
    p = baseline_path(scenario_id, baselines_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"objective": objective}, indent=2) + "\n")
    return p


def check_tier_c(
    scenario_id: str,
    objective: float | None,
    *,
    tolerance: float,
    baselines_dir: Path | None = None,
) -> tuple[str, str]:
    """Returns ``(status, detail)`` — status is PASS/FAIL/PENDING."""
    baseline = load_baseline(scenario_id, baselines_dir)
    if baseline is None:
        return STATUS_PENDING, "no baseline committed yet — review then `scenario-bless`"
    if objective is None:
        return STATUS_FAIL, "no objective to compare (solve produced none)"
    old = baseline["objective"]
    delta = objective - old
    detail = f"old={old:.6f} new={objective:.6f} delta={delta:+.6f} (tolerance {tolerance:.6f})"
    return (STATUS_PASS if abs(delta) <= tolerance else STATUS_FAIL), detail
