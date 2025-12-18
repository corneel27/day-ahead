"""
Electric Vehicle configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class EVChargeStage(BaseModel):
    """Single EV charging stage with amperage and efficiency."""
    
    ampere: int = Field(
        ge=0,
        description="Charging current in amperes"
    )
    efficiency: float = Field(
        ge=0, le=1,
        description="Charging efficiency at this amperage (0-1)"
    )
    
    model_config = ConfigDict(extra='allow')


class EVChargeScheduler(BaseModel):
    """EV charge scheduling configuration."""
    
    entity_set_level: str = Field(
        alias="entity set level",
        description="HA entity to set target charge level"
    )
    level_margin: int = Field(
        alias="level margin",
        ge=0,
        description="Margin in % for charge level completion"
    )
    entity_ready_datetime: str = Field(
        alias="entity ready datetime",
        description="HA entity for ready datetime (when charging should complete)"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )


class EVConfig(BaseModel):
    """Electric Vehicle configuration."""
    
    name: str = Field(
        description="EV name/identifier"
    )
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh"
    )
    entity_position: str = Field(
        alias="entity position",
        description="HA device tracker for vehicle position"
    )
    charge_three_phase: bool | str = Field(
        default=True,
        alias="charge three phase",
        description="Whether vehicle charges on three phases"
    )
    charge_stages: list[EVChargeStage] = Field(
        alias="charge stages",
        min_length=1,
        description="Charging amperage/efficiency curve"
    )
    entity_actual_level: str = Field(
        alias="entity actual level",
        description="HA entity for current battery level %"
    )
    entity_plugged_in: str = Field(
        alias="entity plugged in",
        description="HA binary sensor for plugged in status"
    )
    entity_instant_start: Optional[str] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start charging"
    )
    entity_instant_level: Optional[str] = Field(
        default=None,
        alias="entity instant level",
        description="HA entity for instant charge level target"
    )
    charge_scheduler: Optional[EVChargeScheduler] = Field(
        default=None,
        alias="charge scheduler",
        description="Charge scheduling configuration"
    )
    charge_switch: str = Field(
        alias="charge switch",
        description="HA switch entity to control charging"
    )
    entity_set_charging_ampere: str = Field(
        alias="entity set charging ampere",
        description="HA entity to set charging amperage"
    )
    entity_stop_charging: str = Field(
        alias="entity stop charging",
        description="HA entity for stop charging datetime"
    )
    
    @model_validator(mode='after')
    def validate_charging_method(self) -> 'EVConfig':
        """Ensure either instant charging entities OR charge scheduler is configured."""
        has_instant = self.entity_instant_start is not None and self.entity_instant_level is not None
        has_scheduler = self.charge_scheduler is not None
        
        if not has_instant and not has_scheduler:
            raise ValueError(
                "EV must have either instant charging entities "
                "(entity_instant_start + entity_instant_level) OR charge_scheduler configured"
            )
        
        return self
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
