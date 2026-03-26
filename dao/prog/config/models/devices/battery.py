"""
Battery configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr
from ..base import EntityId, FlexFloat, FlexInt
from .solar import SolarConfig


class BatteryStage(BaseModel):
    """Single charge/discharge stage with power and efficiency."""
    
    power: float = Field(
        ge=0,
        description="Power level in Watts",
        json_schema_extra={
            "x-help": "Power level for this charge/discharge stage. Stages define how battery efficiency changes at different power levels.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Must be 0 or greater, stages should be sorted by power"
        }
    )
    efficiency: float = Field(
        ge=0, le=1,
        description="Efficiency at this power level (0-1)",
        json_schema_extra={
            "x-help": "Energy conversion efficiency at this power level. Value between 0 and 1, where 1 = 100% efficient.",
            "x-unit": "ratio (0-1)",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Must be between 0 and 1"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            "x-help": "Defines power and efficiency at a specific operating point. Multiple stages create a power/efficiency curve.",
            "x-ui-section": "Power Configuration"
        }
    )


class SocPowerLimit(BaseModel):
    """A SOC threshold with a corresponding maximum power limit.

    Used in ``reduce_power_low_soc`` / ``reduce_power_high_soc`` to protect the
    battery by reducing charge/discharge power as SOC approaches its limits.
    Multiple stages define a piecewise-linear power derating curve.
    """

    soc: int = Field(
        ge=0, le=100,
        description="SOC threshold in %",
        json_schema_extra={
            "x-help": "State of Charge threshold at which this power limit applies.",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "0–100 %, stages should be sorted by soc"
        }
    )
    power: int = Field(
        ge=0,
        description="Maximum power at this SOC threshold in watts",
        json_schema_extra={
            "x-help": "Maximum charge or discharge power allowed when SOC is at this threshold.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Must be >= 0"
        }
    )

    # Runtime-only computed attribute (slope between adjacent stages); not persisted.
    _helling: float = PrivateAttr(default=0.0)

    model_config = ConfigDict(extra='forbid')


class BatteryConfig(BaseModel):
    """Battery configuration for optimization."""
    
    name: str = Field(
        description="Battery name/identifier",
        json_schema_extra={
            "x-help": "Unique name to identify this battery in logs and reports. Use a descriptive name like 'Home Battery' or 'Garage Battery'.",
            "x-ui-section": "Power Configuration"
        }
    )
    entity_actual_level: EntityId = Field(
        alias="entity actual level",
        description="HA entity for current battery SOC",
        json_schema_extra={
            "x-help": "Home Assistant entity that reports the current State of Charge (SOC) percentage. Usually a sensor from your battery inverter.",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor"
        }
    )
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh",
        json_schema_extra={
            "x-help": "Total usable energy storage capacity of your battery. Check your battery specifications. For multiple batteries, sum their capacities.",
            "x-unit": "kWh",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Must be greater than 0"
        }
    )
    upper_limit: FlexInt = Field(
        default=FlexInt(value=100),
        alias="upper limit",
        description="Maximum SOC % (can be HA entity)",
        json_schema_extra={
            "x-help": "Maximum State of Charge in percent. Battery will never charge above this level. Supports FlexValue pattern: use integer or HA entity ID.",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "0-100%, protects battery from overcharge"
        }
    )
    lower_limit: FlexInt = Field(
        default=FlexInt(value=20),
        alias="lower limit",
        description="Minimum SOC % (can be HA entity)",
        json_schema_extra={
            "x-help": "Minimum State of Charge in percent. Battery will never discharge below this level. Supports FlexValue pattern: use integer or HA entity ID.",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "0-100%, protects battery from deep discharge"
        }
    )
    optimal_lower_level: Optional[FlexInt] = Field(
        default=None,
        alias="optimal lower level",
        description="Optimal lower SOC % for cost optimization",
        json_schema_extra={
            "x-help": "Target SOC level for cost optimization. System will prefer this level over minimum. Supports FlexValue pattern.",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Optional, should be >= lower_limit"
        }
    )
    penalty_low_soc: float = Field(
        default=0.0025,
        alias="penalty low soc",
        description="Penalty cost per % per hour below optimal lower SOC",
        json_schema_extra={
            "x-help": "Cost in euro per %·hour when SOC stays below optimal lower level. Higher values make the optimizer prioritize keeping SOC above the optimal level. Default 0.0025 euro/%·h.",
            "x-unit": "euro/%·h",
            "x-ui-section": "Power Configuration"
        }
    )
    entity_min_soc_end_opt: Optional[EntityId] = Field(
        default=None,
        alias="entity min soc end opt",
        description="HA entity for minimum SOC at end of optimization period",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity specifying minimum battery level required at end of optimization window. Useful for ensuring battery charge overnight.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor,input_number"
        }
    )
    entity_max_soc_end_opt: Optional[EntityId] = Field(
        default=None,
        alias="entity max soc end opt",
        description="HA entity for maximum SOC at end of optimization period",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity specifying maximum battery level at end of optimization window. Rarely needed but available for advanced scenarios.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor,input_number"
        }
    )
    charge_stages: list[BatteryStage] = Field(
        alias="charge stages",
        min_length=1,
        description="Charge power/efficiency curve",
        json_schema_extra={
            "x-help": "Power stages for charging with corresponding efficiencies. Defines charge curve from AC grid to battery. At least one stage required.",
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "At least 1 stage required, ordered by power"
        }
    )
    discharge_stages: list[BatteryStage] = Field(
        alias="discharge stages",
        min_length=1,
        description="Discharge power/efficiency curve",
        json_schema_extra={
            "x-help": "Power stages for discharging with corresponding efficiencies. Defines discharge curve from battery to AC grid. At least one stage required.",
            "x-ui-section": "Power Configuration",
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
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Keys are hour strings (0-23), values are watts"
        }
    )
    reduce_power_low_soc: list[SocPowerLimit] = Field(
        default_factory=list,
        description="SOC thresholds and power limits for low SOC power reduction",
        json_schema_extra={
            "x-help": "Optional: List of SOC/power pairs to reduce battery power at low state of charge. Protects battery by limiting power when nearly empty.",
            "x-ui-section": "Power Configuration"
        }
    )
    reduce_power_high_soc: list[SocPowerLimit] = Field(
        default_factory=list,
        description="SOC thresholds and power limits for high SOC power reduction",
        json_schema_extra={
            "x-help": "Optional: List of SOC/power pairs to reduce battery power at high state of charge. Protects battery by limiting power when nearly full.",
            "x-ui-section": "Power Configuration"
        }
    )
    minimum_power: int = Field(
        alias="minimum power",
        ge=0,
        description="Minimum power in watts",
        json_schema_extra={
            "x-help": "Minimum power threshold in watts. Operations below this power level will be rounded to zero. Prevents inefficient micro-charging/discharging.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
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
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "0.0-1.0, typically 0.95-0.98"
        }
    )
    dc_to_bat_max_power: Optional[FlexFloat] = Field(
        default=None,
        alias="dc_to_bat max power",
        description="DC to battery max power in watts",
        json_schema_extra={
            "x-help": "Maximum power for DC-coupled solar charging in watts. Determines how much DC solar power can flow directly to battery.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
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
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "0.0-1.0, typically 0.95-0.98"
        }
    )
    bat_to_dc_max_power: Optional[FlexFloat] = Field(
        default=None,
        alias="bat_to_dc max power",
        description="Battery to DC max power in watts",
        json_schema_extra={
            "x-help": "Maximum power for battery to DC bus conversion in watts. Rarely used in typical residential setups.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
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
            "x-ui-section": "Power Configuration",
            "x-validation-hint": "Must be >= 0, typically €0.50-€1.50 per cycle"
        }
    )
    
    # Control entities
    entity_set_power_feedin: Optional[EntityId] = Field(
        default=None,
        alias="entity set power feedin",
        description="HA entity to set power feed-in to grid",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to control grid feed-in power. Used by scheduler to execute optimized battery operations.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "number,input_number"
        }
    )
    entity_set_operating_mode: Optional[EntityId] = Field(
        default=None,
        alias="entity set operating mode",
        description="HA entity to set battery operating mode",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to control battery operating mode (e.g., auto/manual/off). System will switch modes as needed for optimization.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "select,input_select,switch"
        }
    )
    entity_set_operating_mode_on: Optional[str] = Field(
        default="Aan",
        alias="entity set operating mode on",
        description="Value for operating mode ON",
        json_schema_extra={
            "x-help": "Value to send to operating mode entity for 'ON' state. Example: 'auto', 'enabled', 'on'. Must match actual entity values.",
            "x-ui-section": "Power Configuration"
        }
    )
    entity_set_operating_mode_off: Optional[str] = Field(
        default="Uit",
        alias="entity set operating mode off",
        description="Value for operating mode OFF",
        json_schema_extra={
            "x-help": "Value to send to operating mode entity for 'OFF' state. Example: 'manual', 'disabled', 'off'. Must match actual entity values.",
            "x-ui-section": "Power Configuration"
        }
    )
    entity_stop_inverter: Optional[EntityId] = Field(
        default=None,
        alias="entity stop inverter",
        description="HA entity to stop inverter",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to stop the battery inverter. Usefull in situations when the battery is idle and you don't want idle-conusmptions of the battery.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "switch,button"
        }
    )
    entity_balance_switch: Optional[EntityId] = Field(
        default=None,
        alias="entity balance switch",
        description="HA entity for grid balancing switch",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to enable/disable grid balancing mode. Used for frequency regulation participation or grid services.",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "switch"
        }
    )
    
    # Monitoring entities
    entity_from_battery: Optional[EntityId] = Field(
        default=None,
        alias="entity from battery",
        description="HA entity for power from battery",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to save the average power flow from/to battery in watts. Used for battery systems who wants to stear this power in/out.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor"
        }
    )
    entity_from_pv: Optional[EntityId] = Field(
        default=None,
        alias="entity from pv",
        description="HA entity for power from PV",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to save the average calculated DC-coupled solar power in watts. Only relevant for DC-coupled solar installations.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor"
        }
    )
    entity_from_ac: Optional[EntityId] = Field(
        default=None,
        alias="entity from ac",
        description="HA entity for power from AC",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to save the calculated average grid power in watts. For battery systems that want to stear the power in/out.",
            "x-unit": "W",
            "x-ui-section": "Power Configuration",
            "x-ui-widget-filter": "sensor"
        }
    )
    entity_calculated_soc: Optional[EntityId] = Field(
        default=None,
        alias="entity calculated soc",
        description="HA entity for saving calculated SOC",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to save the calculated State of Charge at the end of the first interval. For battery systems that will stear at SoC-values",
            "x-unit": "%",
            "x-ui-section": "Power Configuration",
            "x-order": 1,
            "x-ui-widget-filter": "sensor"
        }
    )
    
    # DC-coupled solar (nested!)
    solar: list[SolarConfig] = Field(
        default_factory=list,
        description="DC-coupled solar panels attached to this battery",
        json_schema_extra={
            "x-help": "Optional: Configure DC-coupled solar panels directly connected to this battery inverter. DC coupling is more efficient than AC coupling. Leave empty for AC-coupled or grid-only batteries.",
            "x-ui-section": "Battery Connected Solar",
            "x-order": 1000
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Energy',
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
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Battery-Configuration'
        }
    )
    
    @field_validator('charge_stages', 'discharge_stages', mode='after')
    @classmethod
    def validate_stages_sorted(cls, v: list[BatteryStage], info) -> list[BatteryStage]:
        """Ensure stages are sorted by power and always start with a zero-power sentinel."""
        powers = [stage.power for stage in v]
        if powers != sorted(powers):
            raise ValueError(f"{info.field_name} must be sorted by power (ascending)")

        if v[0].power != 0.0:
            v = [BatteryStage(power=0.0, efficiency=1.0)] + v

        return v
