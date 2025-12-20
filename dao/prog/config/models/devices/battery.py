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
        description="Power level in Watts",
        json_schema_extra={
            "x-help": "Power level for this charge/discharge stage. Stages define how battery efficiency changes at different power levels.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-validation-hint": "Must be 0 or greater, stages should be sorted by power"
        }
    )
    efficiency: float = Field(
        ge=0, le=1,
        description="Efficiency at this power level (0-1)",
        json_schema_extra={
            "x-help": "Energy conversion efficiency at this power level. Value between 0 and 1, where 1 = 100% efficient.",
            "x-unit": "ratio (0-1)",
            "x-category": "advanced",
            "x-validation-hint": "Must be between 0 and 1"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            "x-help": "Defines power and efficiency at a specific operating point. Multiple stages create a power/efficiency curve.",
            "x-category": "advanced"
        }
    )


class BatteryConfig(BaseModel):
    """Battery configuration for optimization."""
    
    name: str = Field(
        description="Battery name/identifier",
        json_schema_extra={
            "x-help": "Unique name to identify this battery in logs and reports. Use a descriptive name like 'Home Battery' or 'Garage Battery'.",
            "x-category": "basic"
        }
    )
    entity_actual_level: str = Field(
        alias="entity actual level",
        description="HA entity for current battery SOC",
        json_schema_extra={
            "x-help": "Home Assistant entity that reports the current State of Charge (SOC) percentage. Usually a sensor from your battery inverter.",
            "x-unit": "%",
            "x-category": "basic",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh",
        json_schema_extra={
            "x-help": "Total usable energy storage capacity of your battery. Check your battery specifications. For multiple batteries, sum their capacities.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-validation-hint": "Must be greater than 0"
        }
    )
    upper_limit: int | FlexValue = Field(
        alias="upper limit",
        ge=0, le=100,
        description="Maximum SOC % (can be HA entity)"
    )
    lower_limit: int | FlexValue = Field(
        alias="lower limit",
        ge=0, le=100,
        description="Minimum SOC % (can be HA entity)",
        json_schema_extra={
            "x-help": "Minimum State of Charge in percent. Battery will never discharge below this level. Supports FlexValue pattern: use integer or HA entity ID.",
            "x-unit": "%",
            "x-category": "basic",
            "x-validation-hint": "0-100%, protects battery from deep discharge",
            "x-ui-widget": "entity-picker-or-number"
        }
    )
    optimal_lower_level: Optional[int | FlexValue] = Field(
        default=None,
        alias="optimal lower level",
        ge=0, le=100,
        description="Optimal lower SOC % for cost optimization",
        json_schema_extra={
            "x-help": "Target SOC level for cost optimization. System will prefer this level over minimum. Supports FlexValue pattern.",
            "x-unit": "%",
            "x-category": "advanced",
            "x-validation-hint": "Optional, should be >= lower_limit",
            "x-ui-widget": "entity-picker-or-number"
        }
    )
    entity_min_soc_end_opt: Optional[str] = Field(
        default=None,
        alias="entity min soc end opt",
        description="HA entity for minimum SOC at end of optimization period",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity specifying minimum battery level required at end of optimization window. Useful for ensuring battery charge overnight.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor,input_number"
        }
    )
    entity_max_soc_end_opt: Optional[str] = Field(
        default=None,
        alias="entity max soc end opt",
        description="HA entity for maximum SOC at end of optimization period",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity specifying maximum battery level at end of optimization window. Rarely needed but available for advanced scenarios.",
            "x-category": "expert",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor,input_number"
        }
    )
    charge_stages: list[BatteryStage] = Field(
        alias="charge stages",
        min_length=1,
        description="Charge power/efficiency curve",
        json_schema_extra={
            "x-help": "Power stages for charging with corresponding efficiencies. Defines charge curve from AC grid to battery. At least one stage required.",
            "x-category": "basic",
            "x-validation-hint": "At least 1 stage required, ordered by power"
        }
    )
    discharge_stages: list[BatteryStage] = Field(
        alias="discharge stages",
        min_length=1,
        description="Discharge power/efficiency curve",
        json_schema_extra={
            "x-help": "Power stages for discharging with corresponding efficiencies. Defines discharge curve from battery to AC grid. At least one stage required.",
            "x-category": "basic",
            "x-validation-hint": "At least 1 stage required, ordered by power"
        }
    )
    
    # Power reduction
    reduced_hours: Optional[dict[str, int]] = Field(
        default=None,
        alias="reduced hours",
        description="Hour -> max power mapping for reduced power hours",
        json_schema_extra={
            "x-help": "Optional: Restrict battery power during specific hours. Example: {'22': 1000, '23': 1000} limits to 1000W from 22:00-23:59. Useful for noise reduction at night.",
            "x-category": "advanced",
            "x-validation-hint": "Keys are hour strings (0-23), values are watts"
        }
    )
    minimum_power: int = Field(
        alias="minimum power",
        ge=0,
        description="Minimum power in watts",
        json_schema_extra={
            "x-help": "Minimum power threshold in watts. Operations below this power level will be rounded to zero. Prevents inefficient micro-charging/discharging.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-validation-hint": "Must be >= 0, typically 50-200W"
        }
    )
    
    # DC/Battery conversion
    dc_to_bat_efficiency: float = Field(
        alias="dc_to_bat efficiency",
        ge=0, le=1,
        description="DC to battery efficiency",
        json_schema_extra={
            "x-help": "Efficiency of DC-coupled solar to battery conversion. Typically 0.95-0.98 for modern DC-coupled systems. Only relevant if DC-coupled solar is configured.",
            "x-unit": "ratio",
            "x-category": "advanced",
            "x-validation-hint": "0.0-1.0, typically 0.95-0.98"
        }
    )
    dc_to_bat_max_power: float = Field(
        alias="dc_to_bat max power",
        gt=0,
        description="DC to battery max power in watts",
        json_schema_extra={
            "x-help": "Maximum power for DC-coupled solar charging in watts. Determines how much DC solar power can flow directly to battery.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-validation-hint": "Must be > 0"
        }
    )
    bat_to_dc_efficiency: float = Field(
        alias="bat_to_dc efficiency",
        ge=0, le=1,
        description="Battery to DC efficiency",
        json_schema_extra={
            "x-help": "Efficiency of battery to DC bus conversion. Typically 0.95-0.98. Only relevant for DC-coupled loads or reverse DC flow scenarios.",
            "x-unit": "ratio",
            "x-category": "expert",
            "x-validation-hint": "0.0-1.0, typically 0.95-0.98"
        }
    )
    bat_to_dc_max_power: float = Field(
        alias="bat_to_dc max power",
        gt=0,
        description="Battery to DC max power in watts",
        json_schema_extra={
            "x-help": "Maximum power for battery to DC bus conversion in watts. Rarely used in typical residential setups.",
            "x-unit": "W",
            "x-category": "expert",
            "x-validation-hint": "Must be > 0"
        }
    )
    
    # Cost
    cycle_cost: float = Field(
        alias="cycle cost",
        ge=0,
        description="Cost per battery cycle in euros",
        json_schema_extra={
            "x-help": "Degradation cost per full charge-discharge cycle in euros. Used to factor battery wear into optimization. Calculate as: (battery_cost / warranted_cycles). Example: €5000 battery with 6000 cycles = €0.83/cycle.",
            "x-unit": "€",
            "x-category": "basic",
            "x-validation-hint": "Must be >= 0, typically €0.50-€1.50 per cycle"
        }
    )
    
    # Control entities
    entity_set_power_feedin: Optional[str] = Field(
        default=None,
        alias="entity set power feedin",
        description="HA entity to set power feed-in to grid",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to control grid feed-in power. Used by scheduler to execute optimized battery operations.",
            "x-category": "basic",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "number,input_number"
        }
    )
    entity_set_operating_mode: Optional[str] = Field(
        default=None,
        alias="entity set operating mode",
        description="HA entity to set battery operating mode",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to control battery operating mode (e.g., auto/manual/off). System will switch modes as needed for optimization.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "select,input_select,switch",
            "x-related-fields": ["entity_set_operating_mode_on", "entity_set_operating_mode_off"]
        }
    )
    entity_set_operating_mode_on: Optional[str] = Field(
        default=None,
        alias="entity set operating mode on",
        description="Value for operating mode ON",
        json_schema_extra={
            "x-help": "Value to send to operating mode entity for 'ON' state. Example: 'auto', 'enabled', 'on'. Must match actual entity values.",
            "x-category": "advanced",
            "x-related-fields": ["entity_set_operating_mode"]
        }
    )
    entity_set_operating_mode_off: Optional[str] = Field(
        default=None,
        alias="entity set operating mode off",
        description="Value for operating mode OFF",
        json_schema_extra={
            "x-help": "Value to send to operating mode entity for 'OFF' state. Example: 'manual', 'disabled', 'off'. Must match actual entity values.",
            "x-category": "advanced",
            "x-related-fields": ["entity_set_operating_mode"]
        }
    )
    entity_stop_inverter: Optional[str] = Field(
        default=None,
        alias="entity stop inverter",
        description="HA entity to stop inverter",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to emergency stop the battery inverter. Rarely needed but available for safety scenarios.",
            "x-category": "expert",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "switch,button"
        }
    )
    entity_balance_switch: Optional[str] = Field(
        default=None,
        alias="entity balance switch",
        description="HA entity for grid balancing switch",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to enable/disable grid balancing mode. Used for frequency regulation participation or grid services.",
            "x-category": "expert",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "switch"
        }
    )
    
    # Monitoring entities
    entity_from_battery: Optional[str] = Field(
        default=None,
        alias="entity from battery",
        description="HA entity for power from battery",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current power flow from battery in watts. Used for monitoring and validation.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_from_pv: Optional[str] = Field(
        default=None,
        alias="entity from pv",
        description="HA entity for power from PV",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current DC-coupled solar power in watts. Only relevant for DC-coupled solar installations.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_from_ac: Optional[str] = Field(
        default=None,
        alias="entity from ac",
        description="HA entity for power from AC",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current AC grid power flow in watts. Used for monitoring overall system balance.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_calculated_soc: Optional[str] = Field(
        default=None,
        alias="entity calculated soc",
        description="HA entity for calculated SOC",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor for calculated State of Charge. System can compute SOC from power flows if BMS sensor is unavailable.",
            "x-unit": "%",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    
    # DC-coupled solar (nested!)
    solar: Optional[list[SolarConfig]] = Field(
        default=None,
        description="DC-coupled solar panels attached to this battery",
        json_schema_extra={
            "x-help": "Optional: Configure DC-coupled solar panels directly connected to this battery inverter. DC coupling is more efficient than AC coupling. Leave empty for AC-coupled or grid-only batteries.",
            "x-category": "advanced",
            "x-related-fields": ["dc_to_bat_efficiency", "dc_to_bat_max_power"]
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Energy Storage',
            'x-icon': 'battery-charging',
            'x-order': 1,
            'x-help': '''# Battery Configuration

Configure your home battery storage system for optimal energy management and cost savings.

## Key Settings
- **Capacity**: Total storage capacity in kWh
- **SOC Limits**: Upper and lower charge limits to protect battery health
- **Power Stages**: Define charging/discharging efficiency curves
- **Control Entities**: Home Assistant entities to control the battery

## Tips
- Set upper_limit to 80-90% for longer battery life
- Configure charge/discharge stages for accurate optimization
- Monitor battery degradation with cycle_cost setting
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Battery-Configuration',
            'x-category': 'devices',
            'x-collapsible': True
        }
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
