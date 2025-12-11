"""
Graphics/visualization configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class GraphicsConfig(BaseModel):
    """Graphics and visualization settings."""
    
    style: str = Field(
        default="dark_background",
        description="Matplotlib style (e.g., 'dark_background', 'default')"
    )
    show: bool | str = Field(
        default="false",
        description="Whether to show graphics"
    )
    battery_balance: bool | str = Field(
        alias="battery balance",
        default="true",
        description="Show battery balance in graphs"
    )
    prices_consumption: bool | str = Field(
        alias="prices consumption",
        default="true",
        description="Show consumption prices in graphs"
    )
    prices_production: bool | str = Field(
        alias="prices production",
        default="false",
        description="Show production prices in graphs"
    )
    prices_spot: bool | str = Field(
        alias="prices spot",
        default="true",
        description="Show spot prices in graphs"
    )
    average_consumption: bool | str = Field(
        alias="average consumption",
        default="true",
        description="Show average consumption in graphs"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
