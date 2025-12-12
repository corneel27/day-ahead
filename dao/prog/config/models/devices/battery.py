"""
Battery configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from ..base import FlexValue
from .solar import SolarConfig


class BatteryStage(BaseModel):
    """Single charge/discharge stage with power and efficiency."""
    
    power: float = Field(
        ge=0,
        description="Power level in Watts"
    )
    efficiency: float = Field(
        ge=0, le=1,
        description="Efficiency at this power level (0-1)"
    )
    
    model_config = ConfigDict(extra='allow')


class BatteryConfig(BaseModel):
    """Battery configuration for optimization."""
    
    name: str = Field(
        description="Battery name/identifier"
    )
    entity_actual_level: str = Field(
        alias="entity actual level",
        description="HA entity for current battery SOC"
    )
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh"
    )
    upper_limit: int | FlexValue = Field(
        alias="upper limit",
        ge=0, le=100,
        description="Maximum SOC % (can be HA entity)"
    )
    lower_limit: int | FlexValue = Field(
        alias="lower limit",
        ge=0, le=100,
        description="Minimum SOC % (can be HA entity)"
    )
    optimal_lower_level: Optional[int | FlexValue] = Field(
        default=None,
        alias="optimal lower level",
        ge=0, le=100,
        description="Optimal lower SOC % for cost optimization"
    )
    entity_min_soc_end_opt: Optional[str] = Field(
        default=None,
        alias="entity min soc end opt",
        description="HA entity for minimum SOC at end of optimization period"
    )
    entity_max_soc_end_opt: Optional[str] = Field(
        default=None,
        alias="entity max soc end opt",
        description="HA entity for maximum SOC at end of optimization period"
    )
    charge_stages: list[BatteryStage] = Field(
        alias="charge stages",
        min_length=1,
        description="Charge power/efficiency curve"
    )
    discharge_stages: list[BatteryStage] = Field(
        alias="discharge stages",
        min_length=1,
        description="Discharge power/efficiency curve"
    )
    
    # Power reduction
    reduced_hours: Optional[dict[str, int]] = Field(
        default=None,
        alias="reduced hours",
        description="Hour -> max power mapping for reduced power hours"
    )
    minimum_power: int = Field(
        alias="minimum power",
        description="Minimum power in watts"
    )
    
    # DC/Battery conversion
    dc_to_bat_efficiency: float = Field(
        alias="dc_to_bat efficiency",
        ge=0, le=1,
        description="DC to battery efficiency"
    )
    dc_to_bat_max_power: float = Field(
        alias="dc_to_bat max power",
        description="DC to battery max power in watts"
    )
    bat_to_dc_efficiency: float = Field(
        alias="bat_to_dc efficiency",
        ge=0, le=1,
        description="Battery to DC efficiency"
    )
    bat_to_dc_max_power: float = Field(
        alias="bat_to_dc max power",
        description="Battery to DC max power in watts"
    )
    
    # Cost
    cycle_cost: float = Field(
        alias="cycle cost",
        description="Cost per battery cycle in euros"
    )
    
    # Control entities
    entity_set_power_feedin: Optional[str] = Field(
        default=None,
        alias="entity set power feedin",
        description="HA entity to set power feed-in to grid"
    )
    entity_set_operating_mode: Optional[str] = Field(
        default=None,
        alias="entity set operating mode",
        description="HA entity to set battery operating mode"
    )
    entity_set_operating_mode_on: Optional[str] = Field(
        default=None,
        alias="entity set operating mode on",
        description="Value for operating mode ON"
    )
    entity_set_operating_mode_off: Optional[str] = Field(
        default=None,
        alias="entity set operating mode off",
        description="Value for operating mode OFF"
    )
    entity_stop_inverter: Optional[str] = Field(
        default=None,
        alias="entity stop inverter",
        description="HA entity to stop inverter"
    )
    entity_balance_switch: Optional[str] = Field(
        default=None,
        alias="entity balance switch",
        description="HA entity for grid balancing switch"
    )
    
    # Monitoring entities
    entity_from_battery: Optional[str] = Field(
        default=None,
        alias="entity from battery",
        description="HA entity for power from battery"
    )
    entity_from_pv: Optional[str] = Field(
        default=None,
        alias="entity from pv",
        description="HA entity for power from PV"
    )
    entity_from_ac: Optional[str] = Field(
        default=None,
        alias="entity from ac",
        description="HA entity for power from AC"
    )
    entity_calculated_soc: Optional[str] = Field(
        default=None,
        alias="entity calculated soc",
        description="HA entity for calculated SOC"
    )
    
    # DC-coupled solar (nested!)
    solar: Optional[list[SolarConfig]] = Field(
        default=None,
        description="DC-coupled solar panels attached to this battery"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
    
    @field_validator('upper_limit', 'lower_limit', mode='after')
    @classmethod
    def validate_limits(cls, v, info):
        """Ensure limits are reasonable."""
        field_name = info.field_name
        
        # If it's a FlexValue, we can't validate the actual value yet
        if isinstance(v, FlexValue):
            return v
        
        # For literal values, ensure they're in range
        if not (0 <= v <= 100):
            raise ValueError(f"{field_name} must be between 0 and 100")
        
        return v
    
    @field_validator('charge_stages', 'discharge_stages', mode='after')
    @classmethod
    def validate_stages_sorted(cls, v: list[BatteryStage], info) -> list[BatteryStage]:
        """Ensure stages are sorted by power."""
        if len(v) < 2:
            return v
        
        powers = [stage.power for stage in v]
        if powers != sorted(powers):
            raise ValueError(f"{info.field_name} must be sorted by power (ascending)")
        
        return v
