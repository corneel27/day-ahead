"""
Hot water boiler configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class BoilerConfig(BaseModel):
    """Hot water boiler configuration."""
    
    boiler_present: bool | str = Field(
        alias="boiler present",
        description="Whether boiler is present/enabled"
    )
    entity_actual_temp: str = Field(
        alias="entity actual temp.",
        description="HA entity for actual water temperature"
    )
    entity_setpoint: str = Field(
        alias="entity setpoint",
        description="HA entity for temperature setpoint"
    )
    entity_hysterese: str = Field(
        alias="entity hysterese",
        description="HA entity for temperature hysteresis"
    )
    entity_enabled: Optional[str] = Field(
        default=None,
        alias="entity boiler enabled",
        description="HA entity for boiler enabled status"
    )
    entity_instant_start: Optional[str] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start"
    )
    cop: float = Field(
        gt=0,
        description="Coefficient of Performance"
    )
    cooling_rate: float = Field(
        alias="cooling rate",
        ge=0,
        description="Cooling rate in degrees per hour"
    )
    volume: float = Field(
        gt=0,
        description="Water volume in liters"
    )
    heating_allowed_below: float = Field(
        alias="heating allowed below",
        description="Temperature below which heating is allowed"
    )
    elec_power: float = Field(
        alias="elec. power",
        gt=0,
        description="Electrical power in watts"
    )
    activate_service: str = Field(
        alias="activate service",
        description="Service type to activate boiler (e.g., 'press', 'switch')"
    )
    activate_entity: str = Field(
        alias="activate entity",
        description="HA entity to activate boiler"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
