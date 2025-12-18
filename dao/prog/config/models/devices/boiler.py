"""
Hot water boiler configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class BoilerConfig(BaseModel):
    """Hot water boiler configuration."""
    
    boiler_present: bool | str = Field(
        default=True,
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
        default=3.0,
        gt=0,
        description="Coefficient of Performance"
    )
    cooling_rate: float = Field(
        alias="cooling rate",
        ge=0,
        description="Cooling rate in degrees per hour"
    )
    volume: float = Field(
        default=200.0,
        gt=0,
        description="Water volume in liters"
    )
    heating_allowed_below: float = Field(
        alias="heating allowed below",
        description="Temperature below which heating is allowed"
    )
    elec_power: float = Field(
        default=1000.0,
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
    
    @model_validator(mode='after')
    def validate_activate_config(self) -> 'BoilerConfig':
        """Ensure if activate_entity is provided, activate_service must also be provided."""
        # Note: Both fields are required, so this validator is mainly for documentation
        # The actual validation logic in code checks for None on activate_entity
        return self
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
