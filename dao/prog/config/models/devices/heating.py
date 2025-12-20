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
        description="Maximum power in watts for this stage",
        json_schema_extra={
            "x-help": "Maximum electrical power consumption for this heating stage in watts. Heat pumps often have multiple stages (e.g., compressor speeds).",
            "x-unit": "W",
            "x-category": "basic",
            "x-validation-hint": "Must be > 0, stages must be sorted ascending"
        }
    )
    cop: float = Field(
        gt=0,
        description="Coefficient of Performance at this power level",
        json_schema_extra={
            "x-help": "Coefficient of Performance (COP) at this power level. COP = heat_output / electrical_input. Typical values: 3.0-5.0 (3-5x more heat than electricity used).",
            "x-unit": "ratio",
            "x-category": "basic",
            "x-validation-hint": "Must be > 0, typically 2.5-5.5"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            "x-help": "Define heat pump performance curve by power stages and corresponding COP values. Multiple stages allow accurate modeling of variable-speed compressors.",
            "x-category": "basic"
        }
    )


class HeatingConfig(BaseModel):
    """Heating system / heat pump configuration."""
    
    heater_present: bool | str = Field(
        default=False,
        alias="heater present",
        description="Whether heating system is present/enabled",
        json_schema_extra={
            "x-help": "Enable heating system optimization. Set to true to include heat pump in optimization, false to disable. Can also be HA entity ID for dynamic control.",
            "x-category": "basic",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    entity_hp_enabled: Optional[str] = Field(
        default=None,
        alias="entity hp enabled",
        description="HA binary sensor for heat pump enabled status",
        json_schema_extra={
            "x-help": "Optional: Home Assistant binary sensor indicating if heat pump is enabled and operational. System will only optimize when enabled.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "binary_sensor"
        }
    )
    degree_days_factor: float = Field(
        default=1.0,
        alias="degree days factor",
        gt=0,
        description="Degree days factor for heat demand calculation",
        json_schema_extra={
            "x-help": "Multiplier for degree-day heat demand calculation. Adjust based on building insulation and heat loss. Higher = more heat needed. Typical: 0.5-2.0.",
            "x-unit": "factor",
            "x-category": "advanced",
            "x-validation-hint": "Must be > 0, typically 0.5-2.0"
        }
    )
    adjustment: Literal['on/off', 'power', 'heating curve'] = Field(
        default='power',
        description="Adjustment mode",
        json_schema_extra={
            "x-help": "Heat pump control mode: 'on/off' = simple binary control, 'power' = variable power control, 'heating curve' = adjust heating curve based on weather.",
            "x-category": "advanced"
        }
    )
    stages: list[HeatingStage] = Field(
        min_length=1,
        description="Heating power/COP stages",
        json_schema_extra={
            "x-help": "Power and efficiency stages for heat pump. At least one stage required. Multiple stages model variable-speed compressors. Must be sorted by power ascending.",
            "x-category": "basic",
            "x-validation-hint": "At least 1 stage, must be sorted by max_power"
        }
    )
    entity_adjust_heating_curve: Optional[str] = Field(
        default=None,
        alias="entity adjust heating curve",
        description="HA entity to adjust heating curve",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to adjust heating curve. Used when adjustment mode is 'heating curve'. Controls water temperature based on outdoor temperature.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "number,input_number"
        }
    )
    adjustment_factor: Optional[float] = Field(
        default=None,
        alias="adjustment factor",
        description="Factor for heating curve adjustment",
        json_schema_extra={
            "x-help": "Optional: Multiplier for heating curve adjustments. Higher values = more aggressive adjustments. Typical: 0.5-2.0.",
            "x-unit": "factor",
            "x-category": "expert",
            "x-validation-hint": "Typically 0.5-2.0 if specified"
        }
    )
    min_run_length: int = Field(
        default=1,
        alias="min run length",
        ge=1,
        description="Minimum run length in time intervals",
        json_schema_extra={
            "x-help": "Minimum number of consecutive time intervals heat pump must run once started. Prevents excessive on/off cycling which reduces efficiency and equipment life. Typical: 2-4 intervals (2-4 hours).",
            "x-unit": "intervals",
            "x-category": "advanced",
            "x-validation-hint": "Must be >= 1, typically 2-4 for 1h intervals"
        }
    )
    entity_heat_produced: Optional[str] = Field(
        default=None,
        alias="entity hp heat produced",
        description="HA entity for heat produced",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing total heat energy produced. Used for monitoring and validation.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_hp_heat_demand: Optional[str] = Field(
        default=None,
        alias="entity hp heat demand",
        description="HA entity for heat demand",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current heat demand. Can be used instead of degree-day calculation for more accurate demand forecasting.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_avg_temp: Optional[str] = Field(
        default=None,
        alias="entity avg temp",
        description="HA entity for average temperature",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor for outdoor average temperature. Used for degree-day calculations and COP adjustments.",
            "x-unit": "°C",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_hp_cop: Optional[str] = Field(
        default=None,
        alias="entity hp cop",
        description="HA entity for heat pump COP",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current COP. Can be used for monitoring or to override stage-based COP calculations.",
            "x-unit": "ratio",
            "x-category": "expert",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_hp_power: Optional[str] = Field(
        default=None,
        alias="entity hp power",
        description="HA entity for heat pump power",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor showing current electrical power consumption. Used for monitoring and validation.",
            "x-unit": "W",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_hp_switch: Optional[str] = Field(
        default=None,
        alias="entity hp switch",
        description="HA entity to control heat pump on/off",
        json_schema_extra={
            "x-help": "Optional: Home Assistant switch to control heat pump on/off. Used by scheduler to execute optimized heating schedule.",
            "x-category": "basic",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "switch"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Heating & Climate',
            'x-icon': 'heat-pump',
            'x-order': 4,
            'x-help': '''# Heat Pump Configuration

Optimize heat pump operation based on electricity prices, heat demand, and weather conditions.

## Key Concepts

### COP (Coefficient of Performance)
Ratio of heat output to electrical input. Higher is better:
- COP 3.0 = 3 kW heat from 1 kW electricity (300% efficient)
- COP 4.0 = 4 kW heat from 1 kW electricity (400% efficient)
- Varies with outdoor temperature and power level

### Adjustment Modes
- **on/off**: Simple binary control (least flexible)
- **power**: Variable power control (recommended for variable-speed pumps)
- **heating curve**: Adjust water temperature based on outdoor temp (most advanced)

### Stages
Define power levels and corresponding COP values:
- Single stage: Fixed power heat pump
- Multiple stages: Variable-speed compressor with better efficiency
- Must be sorted by power (ascending)

## Tips
- Use degree_days_factor to calibrate heat demand for your building
- Set min_run_length to prevent excessive cycling (2-4h typical)
- Higher COP = cheaper heating, maximize runtime during high-COP conditions
- Consider solar production when scheduling heating loads
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Heat-Pump-Configuration',
            'x-category': 'devices',
            'x-collapsible': True
        }
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
