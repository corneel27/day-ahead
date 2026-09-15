"""Markdown + CSV test reports, absorbed from
``test_ev_harness_v6.write_reports`` and adapted to ``runner.ScenarioResult``
(the failures list already carries both Tier A and case-check failures,
tagged ``[Tier A]``/``[case]`` — see ``runner.run_scenario``)."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .runner import STATUS_ERROR, STATUS_FAIL, STATUS_INFEASIBLE, STATUS_PASS, STATUS_SKIP, ScenarioResult


def write_reports(results: list[ScenarioResult], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"scenario_report_{timestamp}.md"
    csv_path = out_dir / f"scenario_report_{timestamp}.csv"
    md_latest = out_dir / "scenario_report_latest.md"
    csv_latest = out_dir / "scenario_report_latest.csv"

    counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_INFEASIBLE: 0, STATUS_ERROR: 0, STATUS_SKIP: 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines = [f"# Scenario suite report — {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    lines.append(
        f"**{counts[STATUS_PASS]} passed, {counts[STATUS_FAIL]} failed, "
        f"{counts[STATUS_INFEASIBLE]} infeasible, {counts[STATUS_ERROR]} error, "
        f"{counts[STATUS_SKIP]} skipped** out of {len(results)} scenario(s)."
    )
    lines.append("")
    lines.append("| ID | Status | Description | Objective | Scheduled | Min factor | Solve (s / nodes / gap) |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        pt = r.parsed_target
        sched = "—" if pt is None or pt.scheduled is None else str(pt.scheduled)
        minf = "—" if pt is None or pt.min_nonzero_factor is None else f"{pt.min_nonzero_factor:.4f}"
        obj = "—" if r.objective is None else f"{r.objective:.6f}"
        st = r.stats
        solve = "—" if st is None else (
            f"{st.wall_time_sec or '—'} / {st.nodes or '—'} / {st.gap if st.gap is not None else '—'}"
        )
        lines.append(f"| {r.id} | {r.status} | {r.description} | {obj} | {sched} | {minf} | {solve} |")
    lines.append("")

    detail_needed = [r for r in results if not r.ok]
    if detail_needed:
        lines.append("## Details for non-passing scenarios")
        lines.append("")
        for r in detail_needed:
            lines.append(f"### {r.id} — {r.description} ({r.status})")
            if r.failures:
                lines.append("Failures:")
                for f in r.failures:
                    lines.append(f"- {f}")
            if r.parsed_target and r.parsed_target.reason:
                lines.append(f"\nModel's stated reason: `{r.parsed_target.reason}`")
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    md_latest.write_text("\n".join(lines), encoding="utf-8")

    fieldnames = [
        "id", "status", "description", "objective", "scheduled", "reason",
        "energy_needed_kwh", "partial_stops", "boundary_stops", "start_stops",
        "multi_stage_intervals", "duty_slivers", "min_nonzero_factor",
        "min_duty_guard_fired", "wished_level_clipped", "failures",
        "wall_time_sec", "nodes", "gap", "cost_after_optimize",
    ]
    rows = []
    for r in results:
        pt = r.parsed_target
        st = r.stats
        rows.append({
            "id": r.id,
            "status": r.status,
            "description": r.description,
            "objective": r.objective,
            "scheduled": pt.scheduled if pt else None,
            "reason": (pt.reason or "") if pt else "",
            "energy_needed_kwh": pt.energy_needed_kwh if pt else None,
            "partial_stops": pt.partial_stops if pt else None,
            "boundary_stops": pt.boundary_stops if pt else None,
            "start_stops": pt.start_stops if pt else None,
            "multi_stage_intervals": ";".join(pt.multi_stage_intervals) if pt else "",
            "duty_slivers": (";".join(f"{uur}/s{k}/{f:.4f}" for uur, k, f in pt.duty_slivers) if pt else ""),
            "min_nonzero_factor": pt.min_nonzero_factor if pt else None,
            "min_duty_guard_fired": pt.min_duty_guard_fired if pt else None,
            "wished_level_clipped": pt.wished_level_clipped if pt else None,
            "failures": " | ".join(r.failures),
            "wall_time_sec": st.wall_time_sec if st else None,
            "nodes": st.nodes if st else None,
            "gap": st.gap if st else None,
            "cost_after_optimize": st.cost_after_optimize if st else None,
        })
    for path in (csv_path, csv_latest):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return md_path, csv_path
