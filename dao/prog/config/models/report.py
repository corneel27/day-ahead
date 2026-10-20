"""
Reporting configuration models.
"""


from pydantic import BaseModel, ConfigDict, Field

from .base import EntityId


class HaSensorEntry(BaseModel):
    """One report series that DAO writes to a Home Assistant entity."""

    field: str = Field(
        description="Report field to publish",
        json_schema_extra={
            "x-help": "The field as used in the api (/api/report/<field>/...): 'da' (prices), 'consumption', 'production', 'netto_consumption', 'cost', 'profit', 'netto_cost', 'grid', 'cons', 'prod', 'bat_in', 'bat_out', 'base', 'pv_ac', 'pv_dc', 'ev', 'wp', 'boil', 'mach' or 'soc' / 'soc_<n>'.",
        },
    )
    entity: EntityId = Field(
        description="HA entity that receives the data",
        json_schema_extra={
            "x-help": "Home Assistant entity that DAO creates or updates, e.g. 'sensor.dao_prices'. Its state is the value of the current interval; the attribute 'data' holds the whole series in the same format as the api.",
            "x-ui-widget-filter": "sensor",
        },
    )
    column: str | None = Field(
        default=None,
        description="Column used for the state",
        json_schema_extra={
            "x-help": "Optional: column of the data that becomes the state. Default 'value'; for 'da' the default is 'da_cons' (consumption price, other columns: 'da_ex', 'da_prod'), for 'grid' 'netto_consumption'.",
        },
    )
    name: str | None = Field(
        default=None,
        description="Friendly name of the entity",
        json_schema_extra={
            "x-help": "Optional: friendly name shown in Home Assistant. Default 'DAO <field>'.",
        },
    )
    unit: str | None = Field(
        default=None,
        description="Unit of measurement",
        json_schema_extra={
            "x-help": "Optional: unit_of_measurement of the entity. Default: 'EUR/kWh' for prices, 'kWh' for energy per interval, 'EUR' for costs and '%' for soc.",
        },
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class HaSensorsConfig(BaseModel):
    """Report series that DAO writes to Home Assistant entities."""

    include_price_prediction: bool = Field(
        default=False,
        alias="include_price_prediction",
        description="Include values in the price prediction range",
        json_schema_extra={
            "x-help": "When true the series run until the end of the optimization horizon, including the part with predicted prices (prices.prediction.extension). When false they stop at the last known day-ahead price.",
        },
    )
    entities: list[HaSensorEntry] = Field(
        default_factory=list,
        description="Entities that receive report data",
        json_schema_extra={
            "x-help": "List of report fields and the Home Assistant entity each is written to. The data cover today and tomorrow and are written after every optimization and by the task 'push_ha_sensors'.",
        },
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ReportConfig(BaseModel):
    """Reporting and sensor entity configuration."""

    entities_grid_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities grid consumption",
        description="HA entities for grid consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring grid consumption (import). Used for actual vs optimized comparison and reporting.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_grid_production: list[EntityId] = Field(
        default_factory=list,
        alias="entities grid production",
        description="HA entities for grid production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring grid production (export/feed-in). Used for production reporting and solar surplus calculation.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_solar_production_ac: list[EntityId] = Field(
        default_factory=list,
        alias="entities solar production ac",
        description="HA entities for AC solar production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities for AC-coupled solar production. After inverter, directly to AC side. Separate from DC-coupled solar.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_solar_production_dc: list[EntityId] = Field(
        default_factory=list,
        alias="entities solar production dc",
        description="HA entities for DC solar production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities for DC-coupled solar production. Before inverter, directly to battery DC bus. Separate from AC-coupled solar.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_ev_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities ev consumption",
        description="HA entities for EV consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring EV charging consumption. Used for EV-specific energy reporting and cost allocation.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_wp_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities wp consumption",
        description="HA entities for heat pump (warmtepomp) consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring heat pump consumption. Used for heating-specific energy reporting and COP calculation.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_boiler_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities boiler consumption",
        description="HA entities for boiler consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring hot water boiler consumption. Used for boiler-specific energy reporting.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_battery_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities battery consumption",
        description="HA entities for battery consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring battery charging (consumption). Used for battery efficiency and cycling cost calculation.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_battery_production: list[EntityId] = Field(
        default_factory=list,
        alias="entities battery production",
        description="HA entities for battery production",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring battery discharging (production). Used for battery efficiency and round-trip calculation.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    entities_machine_consumption: list[EntityId] = Field(
        default_factory=list,
        alias="entities machine consumption",
        description="HA entities for machine consumption",
        json_schema_extra={
            "x-help": "List of Home Assistant sensor entities measuring appliance/machine consumption (washing machine, dishwasher, etc.). Used for machine-specific reporting.",
            "x-unit": "kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    co2_intensity_sensor: list[EntityId] | None | EntityId | None = Field(
        default=[],
        alias="entity co2-intensity",
        description="HA entity for CO2 intensity",
        json_schema_extra={
            "x-help": "Optional: Home Assistant sensor for grid CO2 intensity (gCO2/kWh). Used to calculate and report carbon footprint of electricity usage.",
            "x-unit": "gCO2/kWh",
            "x-ui-section": "General",
            "x-ui-widget-filter": "sensor",
        },
    )
    sensors: dict | None = Field(
        default=None,
        description="Additional sensors configuration",
        json_schema_extra={
            "x-help": "Optional: Additional custom sensor configurations. Advanced use for extending reporting capabilities beyond standard entities.",
            "x-ui-section": "General",
        },
    )

    ha_sensors: HaSensorsConfig = Field(
        default_factory=HaSensorsConfig,
        alias="ha_sensors",
        description="Report data written to HA entities",
        json_schema_extra={
            "x-help": "Optional: write report series (prices, grid, battery, pv, ...) of today and tomorrow directly to Home Assistant entities, instead of polling the api with REST sensors.",
            "x-ui-section": "HA sensors",
        },
    )

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        loc_by_alias=False,
        json_schema_extra={
            "x-ui-group": "Reporting",
            "x-icon": "chart-bar",
            "x-order": 17,
            "x-help": """# Reporting & Sensors Configuration

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

## HA sensors

DAO can write report series directly to Home Assistant entities:
```json
"ha_sensors": {
  "include_price_prediction": false,
  "entities": [
    {"field": "da", "entity": "sensor.dao_prices"},
    {"field": "consumption", "entity": "sensor.dao_grid_consumption"},
    {"field": "bat_in", "entity": "sensor.dao_battery_in"}
  ]
}
```
The state is the value of the current interval, the attribute `data` holds
today and tomorrow in the format of the api. The entities are written after
every optimization and by the scheduler task `push_ha_sensors`.

## Tips

- Use energy sensors (kWh cumulative)
- Multiple sensors per category are summed
- Essential for accurate cost reporting
- CO2 tracking optional but insightful
- Update when adding new monitoring devices
""",
            "x-docs-url": "https://github.com/corneel27/day-ahead/wiki/Reports",
        },
    )
