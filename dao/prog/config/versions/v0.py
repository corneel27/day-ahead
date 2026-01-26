"""
Version 0 configuration model (root).

This is the main configuration model that ties all sub-models together.
Version 0 represents the initial Pydantic migration - unversioned configs
get migrated to this version with no format changes.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

from ..models.base import SecretStr
from ..models.database import HADatabaseConfig, DatabaseConfig
from ..models.pricing import PricingConfig
from ..models.graphics import GraphicsConfig
from ..models.notifications import NotificationsConfig
from ..models.grid import GridConfig
from ..models.history import HistoryConfig
from ..models.dashboard import DashboardConfig
from ..models.tibber import TibberConfig
from ..models.report import ReportConfig
from ..models.scheduler import SchedulerConfig
from ..models.homeassistant import HomeAssistantConfig
from ..models.devices.battery import BatteryConfig
from ..models.devices.solar import SolarConfig
from ..models.devices.ev import EVConfig
from ..models.devices.boiler import BoilerConfig
from ..models.devices.heating import HeatingConfig
from ..models.devices.machines import MachineConfig


class ConfigurationV0(BaseModel):
    """
    Day Ahead Optimizer Configuration - Version 0.
    
    This is the root configuration model that encompasses all settings.
    """
    
    # Version
    config_version: Literal[0] = 0
    
    # Connection
    homeassistant: HomeAssistantConfig = Field(
        default_factory=lambda: HomeAssistantConfig(),
        description="Home Assistant connection settings"
    )
    
    # Databases
    database_ha: Optional[HADatabaseConfig] = Field(
        default=None,
        alias="database ha",
        description="Home Assistant database connection"
    )
    database_da: Optional[DatabaseConfig] = Field(
        default=None,
        alias="database da",
        description="Day Ahead optimization database connection"
    )
    
    # Location (auto-fetched from HA, but can be in config)
    latitude: Optional[float] = Field(
        default=None,
        description="Latitude (auto-fetched from HA if not set)"
    )
    longitude: Optional[float] = Field(
        default=None,
        description="Longitude (auto-fetched from HA if not set)"
    )
    time_zone: Optional[str] = Field(
        default=None,
        alias="time_zone",
        description="Timezone (auto-fetched from HA if not set)"
    )
    country: Optional[str] = Field(
        default=None,
        description="Country code (auto-fetched from HA if not set)"
    )
    
    # Meteoserver
    meteoserver_key: str | SecretStr = Field(
        alias="meteoserver-key",
        description="Meteoserver API key (can use !secret)"
    )
    meteoserver_model: Literal['harmonie', 'gfs'] = Field(
        default="harmonie",
        alias="meteoserver-model",
        description="Meteoserver model"
    )
    meteoserver_attemps: Optional[int] = Field(
        default=2,
        alias="meteoserver-attemps",
        ge=1,
        description="Number of meteoserver fetch attempts"
    )
    
    # Pricing
    prices: Optional[PricingConfig] = Field(
        default=None,
        description="Day-ahead pricing and tariff configuration"
    )
    
    # General settings
    logging_level: Literal['debug', 'info', 'warning', 'error'] = Field(
        default="info",
        alias="logging level",
        description="Logging level"
    )
    protocol_api: Optional[Literal['http', 'https']] = Field(
        default=None,
        alias="protocol api",
        description="API protocol"
    )
    
    # Baseload
    use_calc_baseload: bool | str = Field(
        default="false",
        alias="use_calc_baseload",
        description="Whether to calculate baseload automatically"
    )
    baseload_calc_periode: int = Field(
        default=56,
        alias="baseload calc periode",
        ge=1,
        description="Period in days for baseload calculation"
    )
    baseload: Optional[float | list[float]] = Field(
        default=None,
        description="Baseload power consumption (watts) - single value or 24 hourly values"
    )
    
    @field_validator('baseload')
    @classmethod
    def validate_baseload_length(cls, v):
        """Validate baseload has exactly 24 values if it's a list."""
        if v is not None and isinstance(v, list):
            if len(v) != 24:
                raise ValueError(f"baseload must have exactly 24 hourly values, got {len(v)}")
        return v
    
    # Graphics
    graphical_backend: str = Field(
        default="",
        alias="graphical backend",
        description="Matplotlib graphical backend"
    )
    graphics: GraphicsConfig = Field(
        default_factory=GraphicsConfig,
        description="Graphics and visualization settings"
    )
    
    # Optimization
    interval: Optional[int | str] = Field(
        default=None,
        description="Optimization interval in minutes"
    )
    strategy: Literal['minimize cost', 'minimize consumption'] = Field(
        default="minimize cost",
        description="Optimization strategy"
    )
    
    # User Interface
    notifications: Optional[NotificationsConfig] = Field(
        default=None,
        description="Notification settings"
    )
    
    # Infrastructure
    grid: GridConfig = Field(
        default_factory=GridConfig,
        description="Grid connection settings"
    )
    history: HistoryConfig = Field(
        default_factory=HistoryConfig,
        description="History retention settings"
    )
    dashboard: DashboardConfig = Field(
        default_factory=DashboardConfig,
        description="Dashboard web UI settings"
    )
    
    # Devices (required arrays)
    battery: list[BatteryConfig] = Field(
        default_factory=list,
        description="Battery configurations"
    )
    solar: list[SolarConfig] = Field(
        default_factory=list,
        description="Solar panel configurations"
    )
    electric_vehicle: list[EVConfig] = Field(
        default_factory=list,
        alias="electric vehicle",
        description="Electric vehicle configurations"
    )
    machines: list[MachineConfig] = Field(
        default_factory=list,
        description="Appliance/machine configurations"
    )
    
    # Optional devices
    boiler: Optional[BoilerConfig] = Field(
        default=None,
        description="Hot water boiler configuration"
    )
    heating: Optional[HeatingConfig] = Field(
        default=None,
        description="Heating system / heat pump configuration"
    )
    
    # Optional integrations
    tibber: Optional[TibberConfig] = Field(
        default=None,
        description="Tibber API integration"
    )
    
    # Reporting & Scheduling
    report: ReportConfig = Field(
        default_factory=ReportConfig,
        description="Reporting entity configuration"
    )
    scheduler: SchedulerConfig = Field(
        default_factory=SchedulerConfig,
        description="Task scheduler configuration"
    )
    
    model_config = ConfigDict(
        extra='allow',  # Preserve unknown keys
        populate_by_name=True  # Allow both snake_case and aliases
    )
