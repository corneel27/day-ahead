"""Formatting helpers for EV charging schedules."""

import datetime as dt
from collections.abc import Sequence


def format_ev_charge_schedule(
    timestamps: Sequence[dt.datetime],
    stage_energy: Sequence[Sequence[float]],
    stage_powers: Sequence[float],
    stage_amperes: Sequence[float],
    calculation_start: dt.datetime,
) -> str:
    """Return the actual EV charging periods and their configured amperage.

    The optimizer stores energy per charging stage, rather than timestamps for
    partial intervals.  For each stage, its run duration is therefore
    ``energy / power``.  A partial interval starts at the beginning of its
    available period, which mirrors the control logic that starts charging now
    and sets a stop time after that duration.
    """
    if len(timestamps) != len(stage_energy):
        raise ValueError("timestamps and stage_energy must have the same length")
    if len(stage_powers) != len(stage_amperes):
        raise ValueError("stage_powers and stage_amperes must have the same length")
    if any(len(energy) != len(stage_powers) for energy in stage_energy):
        raise ValueError("each stage_energy row must contain every charging stage")

    charge_periods: list[tuple[dt.datetime, dt.datetime, float]] = []
    tolerance = 1e-6

    for interval_start, energy_by_stage in zip(timestamps, stage_energy):
        segment_start = max(interval_start, calculation_start)
        for energy_kwh, power_kw, ampere in zip(
            energy_by_stage, stage_powers, stage_amperes
        ):
            if energy_kwh <= tolerance or power_kw <= tolerance or ampere <= 0:
                continue

            segment_end = segment_start + dt.timedelta(
                hours=energy_kwh / power_kw
            )
            if (
                charge_periods
                and charge_periods[-1][2] == ampere
                and abs((segment_start - charge_periods[-1][1]).total_seconds())
                <= 1
            ):
                previous_start, _, previous_ampere = charge_periods[-1]
                charge_periods[-1] = (previous_start, segment_end, previous_ampere)
            else:
                charge_periods.append((segment_start, segment_end, ampere))
            segment_start = segment_end

    if not charge_periods:
        return "Geen laadmomenten ingepland"

    def round_to_minute(value: dt.datetime) -> dt.datetime:
        return (value + dt.timedelta(seconds=30)).replace(second=0, microsecond=0)

    def format_period(start: dt.datetime, end: dt.datetime, ampere: float) -> str:
        start = round_to_minute(start)
        end = round_to_minute(end)
        start_text = start.strftime("%d-%m %H:%M")
        end_text = (
            end.strftime("%H:%M")
            if start.date() == end.date()
            else end.strftime("%d-%m %H:%M")
        )
        return f"{start_text}\N{EN DASH}{end_text} ({ampere:g} A)"

    return ", ".join(
        format_period(start, end, ampere) for start, end, ampere in charge_periods
    )
