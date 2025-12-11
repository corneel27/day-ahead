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
        description="Maximum grid power in kW"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
