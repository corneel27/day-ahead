"""
Reporting configuration models.
"""


from pydantic import BaseModel, ConfigDict, Field

from .base import EntityId


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
    da_ex: EntityId | None = Field(
        default=None,
        description="HA entity for the day-ahead spot price without taxes and markup",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the day-ahead spot price without taxes and markup of today and tomorrow. Not written when not set.",
            "x-unit": "EUR/kWh",
            "x-ui-widget-filter": "sensor",
        },
    )
    da_cons: EntityId | None = Field(
        default=None,
        description="HA entity for the price of consumption (spot price with energy tax, supplier markup and VAT)",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the price of consumption (spot price with energy tax, supplier markup and VAT) of today and tomorrow. Not written when not set.",
            "x-unit": "EUR/kWh",
            "x-ui-widget-filter": "sensor",
        },
    )
    da_prod: EntityId | None = Field(
        default=None,
        description="HA entity for the price of production (feed-in), including a production bonus",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the price of production (feed-in), including a production bonus of today and tomorrow. Not written when not set.",
            "x-unit": "EUR/kWh",
            "x-ui-widget-filter": "sensor",
        },
    )
    consumption: EntityId | None = Field(
        default=None,
        description="HA entity for the grid consumption",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the grid consumption of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    production: EntityId | None = Field(
        default=None,
        description="HA entity for the grid production",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the grid production of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    netto_consumption: EntityId | None = Field(
        default=None,
        description="HA entity for the netto grid consumption (consumption - production)",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the netto grid consumption (consumption - production) of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    cost: EntityId | None = Field(
        default=None,
        description="HA entity for the cost of the grid consumption",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the cost of the grid consumption of today and tomorrow. Not written when not set.",
            "x-unit": "EUR",
            "x-ui-widget-filter": "sensor",
        },
    )
    profit: EntityId | None = Field(
        default=None,
        description="HA entity for the profit of the grid production",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the profit of the grid production of today and tomorrow. Not written when not set.",
            "x-unit": "EUR",
            "x-ui-widget-filter": "sensor",
        },
    )
    netto_cost: EntityId | None = Field(
        default=None,
        description="HA entity for the netto cost (cost - profit)",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the netto cost (cost - profit) of today and tomorrow. Not written when not set.",
            "x-unit": "EUR",
            "x-ui-widget-filter": "sensor",
        },
    )
    cons: EntityId | None = Field(
        default=None,
        description="HA entity for the consumption in the energy balance",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the consumption in the energy balance of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    prod: EntityId | None = Field(
        default=None,
        description="HA entity for the production in the energy balance",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the production in the energy balance of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    bat_in: EntityId | None = Field(
        default=None,
        description="HA entity for the energy into the batteries",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the energy into the batteries of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    bat_out: EntityId | None = Field(
        default=None,
        description="HA entity for the energy out of the batteries",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the energy out of the batteries of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    base: EntityId | None = Field(
        default=None,
        description="HA entity for the baseload",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the baseload of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    pv_ac: EntityId | None = Field(
        default=None,
        description="HA entity for the AC solar production",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the AC solar production of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    pv_dc: EntityId | None = Field(
        default=None,
        description="HA entity for the DC solar production",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the DC solar production of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    ev: EntityId | None = Field(
        default=None,
        description="HA entity for the consumption of the electric vehicles",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the consumption of the electric vehicles of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    wp: EntityId | None = Field(
        default=None,
        description="HA entity for the consumption of the heat pump",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the consumption of the heat pump of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    boil: EntityId | None = Field(
        default=None,
        description="HA entity for the consumption of the boiler",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the consumption of the boiler of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    mach: EntityId | None = Field(
        default=None,
        description="HA entity for the consumption of the machines",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the consumption of the machines of today and tomorrow. Not written when not set.",
            "x-unit": "kW",
            "x-ui-widget-filter": "sensor",
        },
    )
    soc: EntityId | None = Field(
        default=None,
        description="HA entity for the average state of charge of the batteries",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity that receives the average state of charge of the batteries of today and tomorrow. Not written when not set.",
            "x-unit": "%",
            "x-ui-widget-filter": "sensor",
        },
    )

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        json_schema_extra={
            "x-help": "Each entity gets the value of the current interval as state; the attribute 'data' holds today and tomorrow as a list of {time_ts, time, value, datatype}. Entities that are not set are not written. The soc of a single battery is written for extra keys 'soc_0', 'soc_1', ... The entities are written after every optimization and by the task 'push_ha_sensors'.",
        },
    )


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
  "da_cons": "sensor.dao_price_consumption",
  "consumption": "sensor.dao_grid_consumption",
  "bat_in": "sensor.dao_battery_in"
}
```
Only the entities that are set are written. The state is the value of the
current interval, the attribute `data` holds today and tomorrow in the
format of the api. The entities are written after every optimization and by the scheduler task `push_ha_sensors`.

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
