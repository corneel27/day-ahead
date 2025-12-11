"""
Appliance/machine configuration models (washing machine, dishwasher, etc.).
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class MachineProgram(BaseModel):
    """Single machine program with power profile."""
    
    name: str = Field(
        description="Program name (e.g., 'eco', 'quick wash', 'off')"
    )
    power: list[float] = Field(
        description="Power consumption in watts for each time interval"
    )
    
    model_config = ConfigDict(extra='allow')


class MachineConfig(BaseModel):
    """Appliance/machine configuration (washing machine, dishwasher, etc.)."""
    
    name: str = Field(
        description="Machine name/identifier"
    )
    programs: list[MachineProgram] = Field(
        min_length=1,
        description="Available programs with power profiles"
    )
    entity_start_window: str = Field(
        alias="entity start window",
        description="HA entity for start window datetime"
    )
    entity_end_window: str = Field(
        alias="entity end window",
        description="HA entity for end window datetime"
    )
    entity_selected_program: str = Field(
        alias="entity selected program",
        description="HA entity for selected program"
    )
    entity_calculated_start: str = Field(
        alias="entity calculated start",
        description="HA entity for calculated optimal start time"
    )
    entity_calculated_end: str = Field(
        alias="entity calculated end",
        description="HA entity for calculated end time"
    )
    entity_instant_start: Optional[str] = Field(
        default=None,
        alias="entity instant start",
        description="HA entity for instant start"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
