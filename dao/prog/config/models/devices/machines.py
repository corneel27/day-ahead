"""
Appliance/machine configuration models (washing machine, dishwasher, etc.).
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from ..base import EntityId, FlexFloat


class MachineProgram(BaseModel):
    """Single machine program with power profile."""
    
    name: str = Field(
        description="Program name (e.g., 'eco', 'quick wash', 'off')",
        json_schema_extra={
            "x-help": "Descriptive name for this program. Examples: 'eco', 'quick wash', 'intensive', 'off'. Must include an 'off' program with zero power.",
            "x-ui-section": "Machine Specifications"
        }
    )
    power: list[float] = Field(
        description="Power consumption in watts for each time interval",
        json_schema_extra={
            "x-help": "Power profile as list of watts per time interval. Length defines program duration. Example: [2000, 2000, 500, 500, 100] for 5-hour wash cycle.",
            "x-unit": "W",
            "x-ui-section": "Machine Specifications",
            "x-validation-hint": "List of power values, one per interval (typically 1h each)"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            "x-help": "Define power profile for a machine program. Each program has a name and power consumption pattern over time.",
            "x-ui-section": "Machine Specifications"
        }
    )


class MachineConfig(BaseModel):
    """Appliance/machine configuration (washing machine, dishwasher, etc.)."""
    
    name: str = Field(
        description="Machine name/identifier",
        json_schema_extra={
            "x-help": "Unique name for this appliance. Use descriptive names like 'Washing Machine', 'Dishwasher', or 'Dryer' for multiple machines.",
            "x-ui-section": "Machine Specifications"
        }
    )
    programs: list[MachineProgram] = Field(
        min_length=1,
        description="Available programs with power profiles",
        json_schema_extra={
            "x-help": "List of available programs with their power profiles. Must include at least one program. Always include an 'off' program with zero power consumption.",
            "x-ui-section": "Machine Specifications",
            "x-validation-hint": "At least 1 program required, include 'off' program"
        }
    )
    entity_start_window: EntityId = Field(
        alias="entity start window",
        description="HA entity for start window datetime",
        json_schema_extra={
            "x-help": "Home Assistant datetime entity for earliest allowed start time. Machine can start any time after this. Example: 'Now' or '18:00 today'.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
    )
    entity_end_window: EntityId = Field(
        alias="entity end window",
        description="HA entity for end window datetime",
        json_schema_extra={
            "x-help": "Home Assistant datetime entity for latest allowed completion time. Machine must finish before this deadline. Example: '08:00 tomorrow'.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
    )
    entity_selected_program: EntityId = Field(
        alias="entity selected program",
        description="HA entity for selected program",
        json_schema_extra={
            "x-help": "Home Assistant entity to select which program to run. Must match program names defined in 'programs' list.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_select,select"
        }
    )
    entity_calculated_start: EntityId = Field(
        alias="entity calculated start",
        description="HA entity for calculated optimal start time",
        json_schema_extra={
            "x-help": "Home Assistant entity where system writes the calculated optimal start time. User/automation can use this to trigger machine.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
    )
    entity_calculated_end: EntityId = Field(
        alias="entity calculated end",
        description="HA entity for calculated end time",
        json_schema_extra={
            "x-help": "Home Assistant entity where system writes the calculated program end time. Useful for notifications and planning.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
    )
    entity_instant_start: Optional[EntityId] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to force immediate start, bypassing optimization. Useful for urgent wash cycles.",
            "x-ui-section": "Machine Specifications",
            "x-ui-widget-filter": "input_boolean,switch,button"
        }
    )
    flex_cost: FlexFloat = Field(
        default=FlexFloat(value=0.0),
        alias="flex cost",
        description="Flex cost in euro per kwartier (15 min) that the start is delayed",
        json_schema_extra={
            "x-help": "Virtual cost in euro per kwartier (15 minutes) that the calculated start is "
                      "delayed within the planning window. Makes the optimizer prefer an earlier start "
                      "when the cost difference with a later start is small. Set to 0 to disable "
                      "(machine starts purely on lowest cost, regardless of timing). Can be a fixed "
                      "number or a Home Assistant entity ID (e.g. an input_number helper) so you can "
                      "tune it live.",
            "x-unit": "euro/kwartier delay",
            "x-ui-section": "General",
            "x-validation-hint": "Must be >= 0, typically 0.001 - 0.02 euro/kwartier"
        }
    )
    flex_cost_max: FlexFloat = Field(
        default=FlexFloat(value=0.0),
        alias="flex cost max",
        description="Maximum extra cost in euro to let this machine start as early as possible",
        json_schema_extra={
            "x-help": "Budget in euro. When set (> 0), the machine starts at the earliest possible "
                      "time whose total cost does not exceed the cheapest possible cost plus this "
                      "budget — i.e. 'start as early as possible, but never spend more than this much "
                      "extra to do it'. Set to 0 to disable (machine starts purely on lowest cost, "
                      "regardless of timing; 'flex cost' can still be used as a soft tie-breaker). "
                      "Can be a fixed number or a Home Assistant entity ID.",
            "x-unit": "euro",
            "x-ui-section": "General",
            "x-validation-hint": "Must be >= 0. 0 means disabled (only 'flex cost' applies, if set)."
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Devices',
            'x-icon': 'washing-machine',
            'x-order': 6,
            'x-help': '''# Appliance / Machine Configuration

Optimize operation of flexible load appliances (washing machines, dishwashers, dryers, etc.) based on electricity prices and constraints.

## How It Works

The system optimizes when to start appliances within time windows:
1. User sets start window (earliest start) and end window (must finish by)
2. User selects program (each program has a power profile)
3. System calculates optimal start time to minimize cost
4. System writes calculated start time to HA entity
5. User/automation triggers machine at optimal time

## Programs

Each program defines power consumption over time:
- **Power profile**: List of watts per time interval
- **Duration**: Length of power list (e.g., 5 values = 5 hours)
- **'off' program**: Required, with zero power consumption

Examples:
- Eco wash: `[1800, 1800, 400, 400, 100]` (5 hours)
- Quick wash: `[2200, 500, 100]` (3 hours)
- Off: `[]` or `[0]`

## Time Windows

- **Start window**: Earliest allowed start (e.g., "now" or "20:00")
- **End window**: Latest allowed finish (e.g., "08:00 next day")
- System finds cheapest start time within window
- Machine must complete before end window

## Tips

- Define accurate power profiles for each program
- Set realistic time windows (at least program duration)
- Wider time windows = better optimization opportunities
- Combine with solar production forecasts
- Use instant start for urgent loads
- Multiple machines can be optimized together
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Machine-Configuration'
        }
    )
