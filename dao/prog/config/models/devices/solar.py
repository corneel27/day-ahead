"""
Solar configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


class SolarString(BaseModel):
    """Configuration for a single solar panel string."""
    
    tilt: float = Field(
        ge=0, le=90,
        description="Panel tilt angle in degrees (0=horizontal, 90=vertical)"
    )
    orientation: float = Field(
        ge=-180, le=180,
        description="Panel orientation in degrees (0=south, 90=west, -90=east)"
    )
    capacity: float = Field(
        gt=0,
        description="Installed capacity in kWp"
    )
    yield_factor: float = Field(
        alias="yield",
        gt=0,
        description="Yield factor for production calculation"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )


class SolarConfig(BaseModel):
    """Solar panel configuration."""
    
    name: str = Field(
        description="Solar installation name/identifier"
    )
    entity_pv_switch: Optional[str] = Field(
        default=None,
        alias="entity pv switch",
        description="HA entity to enable/disable this solar installation"
    )
    
    # Option 1: Single installation (flat config)
    tilt: Optional[float] = Field(
        default=None,
        ge=0, le=90,
        description="Panel tilt (for single installation)"
    )
    orientation: Optional[float] = Field(
        default=None,
        ge=-180, le=180,
        description="Panel orientation (for single installation)"
    )
    capacity: Optional[float] = Field(
        default=None,
        gt=0,
        description="Installed capacity (for single installation)"
    )
    yield_factor: Optional[float] = Field(
        default=None,
        alias="yield",
        gt=0,
        description="Yield factor (for single installation)"
    )
    
    # Option 2: Multiple strings
    strings: Optional[list[SolarString]] = Field(
        default=None,
        description="Multiple panel strings with different configurations"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
    
    @model_validator(mode='after')
    def validate_config_completeness(self) -> 'SolarConfig':
        """Ensure either flat config or strings are provided."""
        has_flat = all([
            self.tilt is not None,
            self.orientation is not None,
            self.capacity is not None,
            self.yield_factor is not None
        ])
        has_strings = self.strings is not None and len(self.strings) > 0
        
        if not has_flat and not has_strings:
            raise ValueError(
                "Solar configuration must provide either all flat fields "
                "(tilt, orientation, capacity, yield) or strings list"
            )
        
        if has_flat and has_strings:
            raise ValueError(
                "Solar configuration cannot have both flat fields and strings. "
                "Use either flat config OR strings, not both."
            )
        
        return self
    
    @property
    def is_multi_string(self) -> bool:
        """Check if this is a multi-string configuration."""
        return self.strings is not None and len(self.strings) > 0
    
    @property
    def total_capacity(self) -> float:
        """Calculate total capacity across all strings."""
        if self.is_multi_string:
            return sum(s.capacity for s in self.strings)
        return self.capacity or 0.0
