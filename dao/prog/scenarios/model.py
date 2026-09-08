"""In-memory form of a scenario JSON object.

The JSON shape (``dao_scenario_suite_plan.md`` §2/§4) maps onto ``Scenario``
one-to-one. ``expect`` stays a plain dict here — ``expectations.py`` turns
its keys into check objects at run time, so a new assertion is one entry
there and needs no change to this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# S1 supports only these expectation keys. The runner rejects anything else
# so a typo (or an assertion that belongs to a later session) fails loudly
# at load time instead of being silently ignored.
KNOWN_EXPECT_KEYS_S1 = {"solved"}


@dataclass
class Scenario:
    id: str
    description: str

    # solve anchor — "YYYY-MM-DD HH:MM" (naive, on the hour). The frozen
    # clock is pinned here and every hourly array starts here.
    start: str

    # hourly €/kWh. `cons` length defines the horizon in hours. `prod`
    # defaults to `cons`.
    prices_cons: list[float] = field(default_factory=list)
    prices_prod: list[float] | None = None

    # hourly kW total house PV. Defaults to all-zero across the horizon.
    solar: list[float] | None = None

    # hourly kW baseload; flat 0.25 kW when absent.
    baseload: list[float] | None = None
    # hourly outside temperature °C; flat 6.0 when absent.
    temp: list[float] | None = None
    # heat-pump run-hours history fed to get_heatpump_run_hours(); 0 when absent.
    heatpump_hours: float = 0.0

    # entity_id -> state string (layered on base_states.json)
    states: dict[str, Any] = field(default_factory=dict)
    # dotted config path -> value (applied to the sanitised options_example config)
    config_patch: dict[str, Any] = field(default_factory=dict)

    expect: dict[str, Any] = field(default_factory=dict)

    skip: bool = False
    skip_reason: str = ""

    # provenance, filled by the loader
    source_file: str = ""

    @property
    def horizon_hours(self) -> int:
        return len(self.prices_cons)
