"""
Grid configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class GridConfig(BaseModel):
    """Electrical grid connection configuration."""
    
    max_power: float = Field(
        alias="max_power",
        default=17,
        gt=0,
        description="Maximum grid power in kW",
        json_schema_extra={
            "x-help": "Maximum power available from grid connection in kilowatts. Based on your main fuse/circuit breaker rating. Typical residential: 1-phase=7.4kW (32A), 3-phase=17kW (25A) or 25kW (35A). Prevents optimization from exceeding grid capacity.",
            "x-unit": "kW",
            "x-ui-section": "General",
            "x-validation-hint": "Must be > 0, typical 7-25 kW for residential"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Infrastructure',
            'x-icon': 'transmission-tower',
            'x-order': 12,
            'x-help': '''# Grid Connection Configuration

Define electrical grid connection limits to prevent overload.

## Maximum Grid Power

Based on your main fuse/circuit breaker:
- **1-phase 32A**: 7.4 kW (32A × 230V)
- **3-phase 25A**: 17.3 kW (25A × 230V × 3)
- **3-phase 35A**: 24.2 kW (35A × 230V × 3)

## Why This Matters

Optimizer ensures combined consumption never exceeds this limit:
- Prevents main fuse from tripping
- Ensures legal compliance with grid connection
- Coordinates multiple high-power devices (EV, heat pump, boiler)

## Tips

- Check your electrical panel for fuse/breaker rating
- Account for baseload when calculating available power
- System will prioritize loads within this constraint
- Consider upgrade if frequently hitting limits
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Grid-Configuration'
        }
    )
