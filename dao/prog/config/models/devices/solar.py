"""
Solar configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


class SolarString(BaseModel):
    """Configuration for a single solar panel string."""
    
    tilt: float = Field(
        ge=0, le=90,
        description="Panel tilt angle in degrees (0=horizontal, 90=vertical)",
        json_schema_extra={
            "x-help": "Angle of the solar panels relative to horizontal. 0° = flat/horizontal, 30-35° = optimal for Netherlands, 90° = vertical mounting.",
            "x-unit": "degrees",
            "x-category": "basic",
            "x-validation-hint": "Must be between 0 and 90 degrees"
        }
    )
    orientation: float = Field(
        ge=-180, le=180,
        description="Panel orientation in degrees (0=south, 90=west, -90=east)",
        json_schema_extra={
            "x-help": "Compass direction panels are facing. 0° = south (optimal), 90° = west, -90° or 270° = east, 180° = north. South-facing panels produce most energy.",
            "x-unit": "degrees",
            "x-category": "basic",
            "x-validation-hint": "Must be between -180 and 180 degrees"
        }
    )
    capacity: float = Field(
        gt=0,
        description="Installed capacity in kWp",
        json_schema_extra={
            "x-help": "Peak power capacity of this panel string in kilowatt-peak (kWp). Check panel specifications and sum all panels in this string.",
            "x-unit": "kWp",
            "x-category": "basic",
            "x-validation-hint": "Must be greater than 0"
        }
    )
    yield_factor: float = Field(
        alias="yield",
        gt=0,
        description="Yield factor for production calculation",
        json_schema_extra={
            "x-help": "Efficiency factor for this string. Typically 0.8-0.9. Accounts for inverter losses, cable losses, shading, and dirt on panels.",
            "x-unit": "ratio",
            "x-category": "advanced",
            "x-validation-hint": "Must be greater than 0, typically 0.8-0.9"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            "x-help": "Configuration for a single string of solar panels with the same tilt and orientation. Use multiple strings for panels facing different directions.",
            "x-category": "advanced"
        }
    )


class SolarConfig(BaseModel):
    """Solar panel configuration."""
    
    name: str = Field(
        description="Solar installation name/identifier",
        json_schema_extra={
            "x-help": "Unique name for this solar installation. Use descriptive names like 'Roof South' or 'Garage East' for multiple installations.",
            "x-category": "basic"
        }
    )
    entity_pv_switch: Optional[str] = Field(
        default=None,
        alias="entity pv switch",
        description="HA entity to enable/disable this solar installation",
        json_schema_extra={
            "x-help": "Optional Home Assistant entity to enable or disable this solar installation in the optimization. Useful for maintenance or testing.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "switch"
        }
    )
    
    # Option 1: Single installation (flat config)
    tilt: Optional[float] = Field(
        default=None,
        ge=0, le=90,
        description="Panel tilt (for single installation)",
        json_schema_extra={
            "x-help": "Panel tilt angle for simple configuration. Use this OR 'strings', not both. Leave empty if using strings configuration.",
            "x-unit": "degrees",
            "x-category": "basic",
            "x-validation-hint": "0-90 degrees, leave empty when using strings"
        }
    )
    orientation: Optional[float] = Field(
        default=None,
        ge=-180, le=180,
        description="Panel orientation (for single installation)",
        json_schema_extra={
            "x-help": "Panel orientation for simple configuration. Use this OR 'strings', not both. Leave empty if using strings configuration.",
            "x-unit": "degrees",
            "x-category": "basic",
            "x-validation-hint": "-180 to 180 degrees, leave empty when using strings"
        }
    )
    capacity: Optional[float] = Field(
        default=None,
        gt=0,
        description="Installed capacity (for single installation)",
        json_schema_extra={
            "x-help": "Total capacity for simple configuration. Use this OR 'strings', not both. Leave empty if using strings configuration.",
            "x-unit": "kWp",
            "x-category": "basic",
            "x-validation-hint": "Greater than 0, leave empty when using strings"
        }
    )
    yield_factor: Optional[float] = Field(
        default=None,
        alias="yield",
        gt=0,
        description="Yield factor (for single installation)",
        json_schema_extra={
            "x-help": "Yield factor for simple configuration. Use this OR 'strings', not both. Leave empty if using strings configuration.",
            "x-unit": "ratio",
            "x-category": "basic",
            "x-validation-hint": "Greater than 0, typically 0.8-0.9, leave empty when using strings"
        }
    )
    
    # Option 2: Multiple strings
    strings: Optional[list[SolarString]] = Field(
        default=None,
        description="Multiple panel strings with different configurations",
        json_schema_extra={
            "x-help": "Advanced: Configure multiple strings for panels with different orientations or tilts. Use this OR flat config (tilt/orientation/capacity/yield), not both.",
            "x-category": "advanced"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Energy Production',
            'x-icon': 'solar-panel',
            'x-order': 2,
            'x-help': '''# Solar Panel Configuration

Configure your solar panel installations for accurate production forecasting.

## Configuration Options

### Simple Configuration
For panels all facing the same direction, use the flat config:
- **tilt**: Panel angle (0-90°)
- **orientation**: Direction panels face (0=south)
- **capacity**: Total capacity in kWp
- **yield**: Efficiency factor (0.8-0.9)

### Advanced Configuration (Multiple Strings)
For panels facing different directions, use the 'strings' configuration:
- Each string can have different tilt and orientation
- Allows accurate modeling of complex installations
- Example: Panels on both south and east-facing roofs

## Tips
- Use strings configuration for multi-directional installations
- Include all inverter and cable losses in yield factor
- Account for shading in yield factor
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Solar-Configuration',
            'x-category': 'devices',
            'x-collapsible': True
        }
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
