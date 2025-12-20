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
        description="Whether boiler is present/enabled",
        json_schema_extra={
            "x-help": "Enable hot water boiler optimization. Set to true to include boiler in optimization, false to disable. Can also be HA entity ID for dynamic control.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    entity_actual_temp: str = Field(
        alias="entity actual temp.",
        description="HA entity for actual water temperature",
        json_schema_extra={
            "x-help": "Home Assistant sensor showing current hot water temperature in °C. Required for thermal state tracking and heating decisions.",
            "x-unit": "°C",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    entity_setpoint: str = Field(
        alias="entity setpoint",
        description="HA entity for temperature setpoint",
        json_schema_extra={
            "x-help": "Home Assistant entity for target water temperature. System will heat water to this temperature. Typical: 55-65°C for domestic hot water.",
            "x-unit": "°C",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "input_number,number,sensor"
        }
    )
    entity_hysterese: str = Field(
        alias="entity hysterese",
        description="HA entity for temperature hysteresis",
        json_schema_extra={
            "x-help": "Home Assistant entity for temperature hysteresis in °C. Prevents excessive cycling. If setpoint=60°C and hysteresis=5°C, heating starts at 55°C.",
            "x-unit": "°C",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "input_number,number,sensor"
        }
    )
    entity_enabled: Optional[str] = Field(
        default=None,
        alias="entity boiler enabled",
        description="HA entity for boiler enabled status",
        json_schema_extra={
            "x-help": "Optional: Home Assistant binary sensor indicating if boiler is enabled. System will only optimize when boiler is enabled.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "binary_sensor"
        }
    )
    entity_instant_start: Optional[str] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to trigger immediate boiler heating. Overrides optimized schedule for on-demand hot water.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "switch,input_boolean,button"
        }
    )
    cop: float = Field(
        default=3.0,
        gt=0,
        description="Coefficient of Performance",
        json_schema_extra={
            "x-help": "Coefficient of Performance if using heat pump water heater. For resistive heating element, use 1.0. For heat pump water heater, typically 2.5-4.0.",
            "x-unit": "ratio",
            "x-ui-section": "General",
            "x-validation-hint": "Must be > 0, use 1.0 for resistive, 2.5-4.0 for heat pump"
        }
    )
    cooling_rate: float = Field(
        alias="cooling rate",
        ge=0,
        description="Cooling rate in degrees per hour",
        json_schema_extra={
            "x-help": "Rate at which water temperature drops when not heating, in °C per hour. Depends on insulation quality. Typical: 0.5-2.0°C/h for well-insulated boilers.",
            "x-unit": "°C/h",
            "x-ui-section": "General",
            "x-validation-hint": "Must be >= 0, typically 0.5-2.0°C/h"
        }
    )
    volume: float = Field(
        default=200.0,
        gt=0,
        description="Water volume in liters",
        json_schema_extra={
            "x-help": "Hot water tank volume in liters. Affects thermal inertia and heating time. Typical residential: 100-300 liters.",
            "x-unit": "L",
            "x-ui-section": "General",
            "x-validation-hint": "Must be > 0, typically 100-300L"
        }
    )
    heating_allowed_below: float = Field(
        alias="heating allowed below",
        description="Temperature below which heating is allowed",
        json_schema_extra={
            "x-help": "Maximum temperature for starting heating cycle. Heating only occurs when water is below this temperature. Typically same as or slightly above setpoint.",
            "x-unit": "°C",
            "x-ui-section": "General",
            "x-validation-hint": "Should be >= setpoint"
        }
    )
    elec_power: float = Field(
        default=1000.0,
        alias="elec. power",
        gt=0,
        description="Electrical power in watts",
        json_schema_extra={
            "x-help": "Electrical power consumption of heating element or heat pump compressor in watts. Typical: 1000-3000W for resistive, 400-800W for heat pump water heater.",
            "x-unit": "W",
            "x-ui-section": "General",
            "x-validation-hint": "Must be > 0, typically 1000-3000W"
        }
    )
    activate_service: str = Field(
        alias="activate service",
        description="Service type to activate boiler (e.g., 'press', 'switch')",
        json_schema_extra={
            "x-help": "Home Assistant service type to trigger boiler heating. Use 'press' for button entities, 'switch' for switch entities, or custom service names.",
            "x-ui-section": "General"
        }
    )
    activate_entity: str = Field(
        alias="activate entity",
        description="HA entity to activate boiler",
        json_schema_extra={
            "x-help": "Home Assistant entity used to activate boiler heating. System will trigger this entity using activate_service when heating is needed.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "button,switch"
        }
    )
    
    @model_validator(mode='after')
    def validate_activate_config(self) -> 'BoilerConfig':
        """Ensure if activate_entity is provided, activate_service must also be provided."""
        # Note: Both fields are required, so this validator is mainly for documentation
        # The actual validation logic in code checks for None on activate_entity
        return self
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Heating & Climate',
            'x-icon': 'water-boiler',
            'x-order': 5,
            'x-help': '''# Hot Water Boiler Configuration

Optimize hot water heating based on electricity prices, usage patterns, and thermal characteristics.

## How It Works

The system models boiler as a thermal battery:
- Water stores heat energy based on volume and temperature
- Heat is lost over time based on cooling_rate
- System schedules heating during cheap electricity periods
- Ensures hot water availability when needed

## Key Parameters

### Temperature Control
- **setpoint**: Target temperature (typically 55-65°C)
- **hysterese**: Dead band to prevent cycling (typically 3-5°C)
- **heating_allowed_below**: Max temp to start heating

### Physical Properties
- **volume**: Tank size affects how much heat can be stored
- **cooling_rate**: Heat loss rate (better insulation = lower rate)
- **elec_power**: Heating power affects heating duration
- **cop**: Efficiency (1.0 for resistive, 2.5-4.0 for heat pump)

### Activation
- **activate_entity**: Button/switch to trigger heating
- **activate_service**: Service type ('press' or 'switch')

## Tips
- Larger volume = more thermal storage capacity
- Better insulation = lower cooling_rate = more flexibility
- Heat pump water heaters (COP > 1.0) much more efficient than resistive
- Schedule heating during solar production or cheap grid periods
- Instant start available for emergency hot water needs
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Boiler-Configuration'
        }
    )
