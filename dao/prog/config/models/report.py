"""
Reporting configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ReportConfig(BaseModel):
    """Reporting and sensor entity configuration."""
    
    entities_grid_consumption: list[str] = Field(
        default_factory=list,
        alias="entities grid consumption",
        description="HA entities for grid consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring grid consumption (import). Used for actual vs optimized comparison and reporting.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_grid_production: list[str] = Field(
        default_factory=list,
        alias="entities grid production",
        description="HA entities for grid production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring grid production (export/feed-in). Used for production reporting and solar surplus calculation.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_solar_production_ac: list[str] = Field(
        default_factory=list,
        alias="entities solar production ac",
        description="HA entities for AC solar production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities for AC-coupled solar production. After inverter, directly to AC side. Separate from DC-coupled solar.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_solar_production_dc: list[str] = Field(
        default_factory=list,
        alias="entities solar production dc",
        description="HA entities for DC solar production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities for DC-coupled solar production. Before inverter, directly to battery DC bus. Separate from AC-coupled solar.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_ev_consumption: list[str] = Field(
        default_factory=list,
        alias="entities ev consumption",
        description="HA entities for EV consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring EV charging consumption. Used for EV-specific energy reporting and cost allocation.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_wp_consumption: list[str] = Field(
        default_factory=list,
        alias="entities wp consumption",
        description="HA entities for heat pump (warmtepomp) consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring heat pump consumption. Used for heating-specific energy reporting and COP calculation.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_boiler_consumption: list[str] = Field(
        default_factory=list,
        alias="entities boiler consumption",
        description="HA entities for boiler consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring hot water boiler consumption. Used for boiler-specific energy reporting.",
            "x-unit": "kWh",
            "x-category": "basic",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_battery_consumption: list[str] = Field(
        default_factory=list,
        alias="entities battery consumption",
        description="HA entities for battery consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring battery charging (consumption). Used for battery efficiency and cycling cost calculation.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_battery_production: list[str] = Field(
        default_factory=list,
        alias="entities battery production",
        description="HA entities for battery production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring battery discharging (production). Used for battery efficiency and round-trip calculation.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    entities_machine_consumption: list[str] = Field(
        default_factory=list,
        alias="entities machine consumption",
        description="HA entities for machine consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring appliance/machine consumption (washing machine, dishwasher, etc.). Used for machine-specific reporting.",
            "x-unit": "kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-list-picker",
            "x-entity-filter": "sensor"
        }
    )
    co2_intensity_sensor: Optional[str] = Field(
        default=None,
        alias="co2 intensity sensor",
        description="HA entity for CO2 intensity",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor for grid CO2 intensity (gCO2/kWh). Used to calculate and report carbon footprint of electricity usage.",
            "x-unit": "gCO2/kWh",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "sensor"
        }
    )
    sensors: Optional[dict] = Field(
        default=None,
        description="Additional sensors configuration",
        json_schema_extra={
            "x-help": "Optional: Additional custom sensor configurations. Advanced use for extending reporting capabilities beyond standard entities.",
            "x-category": "expert"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Reporting',
            'x-icon': 'chart-bar',
            'x-order': 17,
            'x-help': '''# Reporting & Sensors Configuration

Configure Home Assistant sensors for comprehensive energy reporting.

## Purpose

Connect actual energy measurements to Day Ahead Optimizer:
- Compare actual vs optimized usage
- Track device-specific consumption
- Calculate efficiency metrics
- Generate cost reports
- Monitor carbon footprint

## Entity Lists

All entity fields accept lists of HA sensors:
```json
"entities_grid_consumption": [
  "sensor.grid_import_meter",
  "sensor.backup_meter"
]
```

## Key Measurements

### Grid
- **Consumption**: Total import from grid
- **Production**: Total export/feed-in to grid

### Solar
- **AC**: After inverter, to AC distribution
- **DC**: Before inverter, directly to battery

### Devices
- **EV**: Charging consumption
- **Heat Pump**: Heating/cooling consumption
- **Boiler**: Hot water heating consumption
- **Battery**: Charge/discharge tracking
- **Machines**: Appliance consumption

## Tips

- Use energy sensors (kWh cumulative)
- Multiple sensors per category are summed
- Essential for accurate cost reporting
- CO2 tracking optional but insightful
- Update when adding new monitoring devices
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Reporting-Configuration',
            'x-category': 'reporting',
            'x-collapsible': True
        }
    )
