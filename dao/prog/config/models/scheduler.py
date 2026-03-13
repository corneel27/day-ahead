"""
Scheduler configuration models.
"""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


# Valid scheduler actions
SchedulerAction = Literal[
    'get_meteo_data',
    'get_tibber_data',
    'get_day_ahead_prices',
    'calc_optimum',
    'clean_data',
    'calc_baseloads',
    'train_ml_predictions'
]


class ScheduleEntry(BaseModel):
    """A single scheduled task entry."""

    time: str = Field(
        description="Time pattern in HHMM format",
        json_schema_extra={
            "x-help": "Time pattern: specific time like '0435' or wildcard like 'xx00' (every hour at :00)",
            "x-validation-hint": "Format: HHMM (24-hour, e.g., '0435', 'xx15')"
        }
    )
    action: SchedulerAction = Field(
        description="Action to execute at this time",
        json_schema_extra={
            "x-help": "Task to run: data collection, optimization, or maintenance"
        }
    )

    @field_validator('time')
    @classmethod
    def validate_time_pattern(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) != 4:
            raise ValueError("Time pattern must be 4 characters (HHMM format)")
        if not (v.isdigit() or (v[0:2] == 'xx' and v[2:4].isdigit())):
            raise ValueError("Time must be HHMM digits or 'xx' wildcard for hours")
        if v[0:2] != 'xx':
            hour = int(v[0:2])
            if hour > 23:
                raise ValueError("Hour must be between 00 and 23")
        minute = int(v[2:4])
        if minute > 59:
            raise ValueError("Minute must be between 00 and 59")
        return v


class SchedulerConfig(BaseModel):
    """Task scheduler configuration."""

    active: bool = Field(
        default=False,
        description="Enable or disable the scheduler",
        json_schema_extra={
            "x-help": "When enabled, scheduled tasks will run automatically at configured times. Disable to prevent all scheduled tasks from running.",
            "x-ui-section": "Scheduler",
            "x-order": 1
        }
    )
    schedule: list[ScheduleEntry] = Field(
        default_factory=list,
        description="Scheduled task entries",
        json_schema_extra={
            "x-help": "Define when tasks should run. Add entries with time patterns (e.g., '0435', 'xx00') and actions.",
            "x-ui-section": "Scheduler",
            "x-order": 2
        }
    )
    model_config = ConfigDict(
        json_schema_extra={
            'x-ui-group': 'DAO',
            'x-order': 18,
            'x-icon': 'clock-outline',
            'x-help': '''# Scheduler Configuration

Define when automatic tasks run using time patterns.

## Time Pattern Format

- **Specific time**: "0435" (4:35 AM), "1255" (12:55 PM)
- **Hourly wildcard**: "xx00" (every hour at :00), "xx15" (every hour at :15)
- **Format**: HHMM (24-hour, no colons)

## Available Actions

### Data Collection
- **get_meteo_data**: Fetch weather forecasts (solar irradiation, temperature)
- **get_tibber_data**: Fetch Tibber prices (if using Tibber)
- **get_day_ahead_prices**: Fetch day-ahead market prices

### Optimization
- **calc_optimum**: Run main optimization algorithm
- **calc_baseloads**: Calculate baseline consumption from history

### Maintenance
- **clean_data**: Clean up old data (runs save_days retention)

## Example Configuration

```json
{
  "active": true,
  "schedule": [
    {"time": "0435", "action": "get_day_ahead_prices"},
    {"time": "0445", "action": "get_meteo_data"},
    {"time": "0500", "action": "calc_optimum"},
    {"time": "xx00", "action": "calc_baseloads"},
    {"time": "0300", "action": "clean_data"}
  ]
}
```

## Typical Schedule

1. **04:00-05:00**: Fetch prices and weather (after day-ahead auction)
2. **05:00**: Run optimization with fresh data
3. **Hourly**: Update baseload calculations
4. **03:00**: Clean old data (low activity time)

## Tips

- Day-ahead prices available after ~13:00 (CET) for next day
- Run optimization after all data fetched
- Hourly baseload updates improve accuracy
- Clean data during low activity (night)
- Avoid overlapping long-running tasks
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Scheduler'
        }
    )
