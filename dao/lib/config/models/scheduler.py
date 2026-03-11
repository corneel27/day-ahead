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

    time: str = Field(description="Time pattern in HHMM format")
    action: SchedulerAction = Field(description="Action to execute at this time")

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
        json_schema_extra={"x-ui-section": "Scheduler", "x-order": 1}
    )
    schedule: list[ScheduleEntry] = Field(
        default_factory=list,
        description="Scheduled task entries",
        json_schema_extra={"x-ui-section": "Scheduler", "x-order": 2}
    )
    model_config = ConfigDict(
        json_schema_extra={
            "x-ui-group": "DAO",
            "x-order": 18,
            "x-icon": "clock-outline",
            "x-docs-url": "https://github.com/corneel27/day-ahead/wiki/Scheduler"
        }
    )
