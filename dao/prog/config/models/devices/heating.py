"""
Heating system / heat pump configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class HeatingStage(BaseModel):
    """Single heating stage with power and COP."""
    
    max_power: float = Field(
        alias="max_power",
        gt=0,
        description="Maximum power in watts for this stage"
    )
    cop: float = Field(
        gt=0,
        description="Coefficient of Performance at this power level"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )


class HeatingConfig(BaseModel):
    """Heating system / heat pump configuration."""
    
    heater_present: bool | str = Field(
        alias="heater present",
        description="Whether heating system is present/enabled"
    )
    entity_hp_enabled: str = Field(
        alias="entity hp enabled",
        description="HA binary sensor for heat pump enabled status"
    )
    degree_days_factor: float = Field(
        alias="degree days factor",
        gt=0,
        description="Degree days factor for heat demand calculation"
    )
    adjustment: Literal['on/off', 'power', 'heating curve'] = Field(
        description="Adjustment mode"
    )
    stages: list[HeatingStage] = Field(
        min_length=1,
        description="Heating power/COP stages"
    )
    entity_adjust_heating_curve: Optional[str] = Field(
        default=None,
        alias="entity adjust heating curve",
        description="HA entity to adjust heating curve"
    )
    adjustment_factor: Optional[float] = Field(
        default=None,
        alias="adjustment factor",
        description="Factor for heating curve adjustment"
    )
    min_run_length: Optional[int] = Field(
        default=None,
        alias="min run length",
        ge=1,
        description="Minimum run length in time intervals"
    )
    entity_heat_produced: Optional[str] = Field(
        default=None,
        alias="entity hp heat produced",
        description="HA entity for heat produced"
    )
    entity_hp_heat_demand: Optional[str] = Field(
        default=None,
        alias="entity hp heat demand",
        description="HA entity for heat demand"
    )
    entity_avg_temp: Optional[str] = Field(
        default=None,
        alias="entity avg temp",
        description="HA entity for average temperature"
    )
    entity_hp_cop: Optional[str] = Field(
        default=None,
        alias="entity hp cop",
        description="HA entity for heat pump COP"
    )
    entity_hp_power: Optional[str] = Field(
        default=None,
        alias="entity hp power",
        description="HA entity for heat pump power"
    )
    entity_hp_switch: Optional[str] = Field(
        default=None,
        alias="entity hp switch",
        description="HA entity to control heat pump on/off"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
    
    @field_validator('stages', mode='after')
    @classmethod
    def validate_stages_sorted(cls, v: list[HeatingStage]) -> list[HeatingStage]:
        """Ensure stages are sorted by power."""
        if len(v) < 2:
            return v
        
        powers = [stage.max_power for stage in v]
        if powers != sorted(powers):
            raise ValueError("Heating stages must be sorted by max_power (ascending)")
        
        return v
