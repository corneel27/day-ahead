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
        description="HA entities for grid consumption"
    )
    entities_grid_production: list[str] = Field(
        default_factory=list,
        alias="entities grid production",
        description="HA entities for grid production"
    )
    entities_solar_production_ac: list[str] = Field(
        default_factory=list,
        alias="entities solar production ac",
        description="HA entities for AC solar production"
    )
    entities_solar_production_dc: list[str] = Field(
        default_factory=list,
        alias="entities solar production dc",
        description="HA entities for DC solar production"
    )
    entities_ev_consumption: list[str] = Field(
        default_factory=list,
        alias="entities ev consumption",
        description="HA entities for EV consumption"
    )
    entities_wp_consumption: list[str] = Field(
        default_factory=list,
        alias="entities wp consumption",
        description="HA entities for heat pump (warmtepomp) consumption"
    )
    entities_boiler_consumption: list[str] = Field(
        default_factory=list,
        alias="entities boiler consumption",
        description="HA entities for boiler consumption"
    )
    entities_battery_consumption: list[str] = Field(
        default_factory=list,
        alias="entities battery consumption",
        description="HA entities for battery consumption"
    )
    entities_battery_production: list[str] = Field(
        default_factory=list,
        alias="entities battery production",
        description="HA entities for battery production"
    )
    entities_machine_consumption: list[str] = Field(
        default_factory=list,
        alias="entities machine consumption",
        description="HA entities for machine consumption"
    )
    co2_intensity_sensor: Optional[str] = Field(
        default=None,
        alias="co2 intensity sensor",
        description="HA entity for CO2 intensity"
    )
    sensors: Optional[dict] = Field(
        default=None,
        description="Additional sensors configuration"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
