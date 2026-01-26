"""
Electric Vehicle configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class EVChargeStage(BaseModel):
    """Single EV charging stage with amperage and efficiency."""
    
    ampere: int = Field(
        ge=0,
        description="Charging current in amperes",
        json_schema_extra={
            "x-help": "Charging current in amperes for this stage. Typical values: 6A (1.4kW), 10A (2.3kW), 16A (3.7kW), 32A (7.4kW) for single-phase.",
            "x-unit": "A",
            "x-ui-section": "General",
            "x-validation-hint": "Must be >= 0, typically 6-32A"
        }
    )
    efficiency: float = Field(
        ge=0, le=1,
        description="Charging efficiency at this amperage (0-1)",
        json_schema_extra={
            "x-help": "Charging efficiency ratio at this amperage level. Accounts for charger losses, cable losses, and battery acceptance. Typically 0.85-0.95.",
            "x-unit": "ratio",
            "x-ui-section": "General",
            "x-validation-hint": "0.0-1.0, typically 0.85-0.95"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            "x-help": "Define charging curve by specifying amperage and efficiency pairs. Multiple stages allow accurate modeling of variable efficiency.",
            "x-ui-section": "General"
        }
    )


class EVChargeScheduler(BaseModel):
    """EV charge scheduling configuration."""
    
    entity_set_level: str = Field(
        alias="entity set level",
        description="HA entity to set target charge level",
        json_schema_extra={
            "x-help": "Home Assistant entity to set the target battery level for scheduled charging. System will optimize when to charge to reach this level.",
            "x-unit": "%",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "input_number,number"
        }
    )
    level_margin: int = Field(
        alias="level margin",
        ge=0,
        description="Margin in % for charge level completion",
        json_schema_extra={
            "x-help": "Acceptable margin below target level. Example: target=80%, margin=5% means 75-80% is acceptable. Provides flexibility in optimization.",
            "x-unit": "%",
            "x-ui-section": "General",
            "x-validation-hint": "Must be >= 0, typically 5-10%"
        }
    )
    entity_ready_datetime: str = Field(
        alias="entity ready datetime",
        description="HA entity for ready datetime (when charging should complete)",
        json_schema_extra={
            "x-help": "Home Assistant datetime entity specifying when vehicle must be charged. System will optimize charging schedule to minimize cost while meeting deadline.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            "x-help": "Advanced scheduler that optimizes charging to reach target level by specific deadline, minimizing cost by charging during cheapest hours.",
            "x-ui-section": "General"
        }
    )


class EVConfig(BaseModel):
    """Electric Vehicle configuration."""
    
    name: str = Field(
        description="EV name/identifier",
        json_schema_extra={
            "x-help": "Unique name for this electric vehicle. Use descriptive names like 'Tesla Model 3' or 'Polestar 2' for multiple vehicles.",
            "x-ui-section": "General"
        }
    )
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh",
        json_schema_extra={
            "x-help": "Usable battery capacity in kilowatt-hours. Check vehicle specifications (often less than advertised total capacity).",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-validation-hint": "Must be > 0, typically 40-100 kWh"
        }
    )
    entity_position: str = Field(
        alias="entity position",
        description="HA device tracker for vehicle position",
        json_schema_extra={
            "x-help": "Home Assistant device tracker entity to detect if vehicle is home. Charging is only scheduled when vehicle is at home location.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "device_tracker"
        }
    )
    charge_three_phase: bool | str = Field(
        default=True,
        alias="charge three phase",
        description="Whether vehicle charges on three phases",
        json_schema_extra={
            "x-help": "True for three-phase charging (11kW/22kW), False for single-phase (3.7kW/7.4kW). Can also be HA entity ID for dynamic resolution.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    charge_stages: list[EVChargeStage] = Field(
        alias="charge stages",
        min_length=1,
        description="Charging amperage/efficiency curve",
        json_schema_extra={
            "x-help": "Charging curve defined by amperage stages and their efficiencies. At least one stage required. Multiple stages enable optimization of charging speed.",
            "x-ui-section": "General",
            "x-validation-hint": "At least 1 stage required"
        }
    )
    entity_actual_level: str = Field(
        alias="entity actual level",
        description="HA entity for current battery level %",
        json_schema_extra={
            "x-help": "Home Assistant sensor showing current battery State of Charge in percent. Required for charge optimization.",
            "x-unit": "%",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "sensor"
        }
    )
    entity_plugged_in: str = Field(
        alias="entity plugged in",
        description="HA binary sensor for plugged in status",
        json_schema_extra={
            "x-help": "Home Assistant binary sensor indicating if vehicle is plugged into charger. Charging is only possible when plugged in.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "binary_sensor"
        }
    )
    entity_instant_start: Optional[str] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start charging",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to trigger immediate charging. Use with entity_instant_level for instant charging mode. Alternative to charge_scheduler.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "switch,input_boolean"
        }
    )
    entity_instant_level: Optional[str] = Field(
        default=None,
        alias="entity instant level",
        description="HA entity for instant charge level target",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity for instant charge target level. When instant_start triggers, system charges to this level immediately. Alternative to charge_scheduler.",
            "x-unit": "%",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "input_number,number,sensor"
        }
    )
    charge_scheduler: Optional[EVChargeScheduler] = Field(
        default=None,
        alias="charge scheduler",
        description="Charge scheduling configuration",
        json_schema_extra={
            "x-help": "Optional: Advanced scheduler for time-based charging. Optimizes when to charge to meet deadline at lowest cost. Alternative to instant charging.",
            "x-ui-section": "General"
        }
    )
    charge_switch: str = Field(
        alias="charge switch",
        description="HA switch entity to control charging",
        json_schema_extra={
            "x-help": "Home Assistant switch entity to start/stop charging. System will control this to execute optimized charging schedule.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "switch"
        }
    )
    entity_set_charging_ampere: str = Field(
        alias="entity set charging ampere",
        description="HA entity to set charging amperage",
        json_schema_extra={
            "x-help": "Home Assistant entity to control charging current in amperes. System will adjust this to optimize charging speed and cost.",
            "x-unit": "A",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "number,input_number"
        }
    )
    entity_stop_charging: str = Field(
        alias="entity stop charging",
        description="HA entity for stop charging datetime",
        json_schema_extra={
            "x-help": "Home Assistant datetime entity specifying when to stop charging. Provides manual override of optimized schedule.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker",
            "x-ui-widget-filter": "input_datetime,datetime"
        }
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
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Devices',
            'x-icon': 'car-electric',
            'x-order': 3,
            'x-help': '''# Electric Vehicle Configuration

Optimize EV charging based on electricity prices, solar production, and charging deadlines.

## Charging Modes

### Instant Charging
Use `entity_instant_start` + `entity_instant_level` for immediate charging:
- Trigger instant_start to charge now
- System charges to instant_level immediately
- Simpler but less cost-optimized

### Scheduled Charging
Use `charge_scheduler` for time-based optimization:
- Set target level and ready datetime
- System optimizes when to charge for lowest cost
- Ensures vehicle is ready by deadline
- More complex but better cost optimization

## Requirements
- Must configure EITHER instant charging OR scheduler (not both)
- Vehicle must be home (device tracker)
- Vehicle must be plugged in (binary sensor)
- Charger must support amperage control

## Tips
- Use multiple charge stages for better efficiency modeling
- Three-phase charging (11/22kW) much faster than single-phase (3.7/7.4kW)
- Consider time-of-use tariffs when setting charge deadlines
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/EV-Configuration'
        }
    )
