"""
Graphics/visualization configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class GraphicsConfig(BaseModel):
    """Graphics and visualization settings."""
    
    style: str = Field(
        default="dark_background",
        description="Matplotlib style (e.g., 'dark_background', 'default')",
        json_schema_extra={
            "x-help": "Matplotlib visual style for generated graphs. 'dark_background' matches Home Assistant dark theme. Other options: 'default', 'seaborn', 'ggplot', 'bmh', 'fivethirtyeight'.",
            "x-ui-section": "General"
        }
    )
    show: bool | str = Field(
        default="false",
        description="Whether to show graphics",
        json_schema_extra={
            "x-help": "Enable graph generation and display. Graphs show optimization results, prices, battery schedules. Set to true to enable, false to disable. Can be HA entity ID.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    battery_balance: bool | str = Field(
        alias="battery balance",
        default="true",
        description="Show battery balance in graphs",
        json_schema_extra={
            "x-help": "Display battery state of charge and power flows in graphs. Shows charge/discharge schedule over time.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    prices_consumption: bool | str = Field(
        alias="prices consumption",
        default="true",
        description="Show consumption prices in graphs",
        json_schema_extra={
            "x-help": "Display consumption prices (market + taxes + VAT) in graphs. Helps visualize expensive vs cheap periods.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    prices_production: bool | str = Field(
        alias="prices production",
        default="false",
        description="Show production prices in graphs",
        json_schema_extra={
            "x-help": "Display feed-in/production prices in graphs. Useful if you have solar feed-in to compare consumption vs production value.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    prices_spot: bool | str = Field(
        alias="prices spot",
        default="true",
        description="Show spot prices in graphs",
        json_schema_extra={
            "x-help": "Display raw day-ahead spot market prices (before taxes/markup) in graphs. Shows pure market price variations.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    average_consumption: bool | str = Field(
        alias="average consumption",
        default="true",
        description="Show average consumption in graphs",
        json_schema_extra={
            "x-help": "Display average/baseline consumption in graphs. Helps understand optimization impact relative to normal usage.",
            "x-ui-section": "General",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Visualization',
            'x-icon': 'chart-line',
            'x-order': 13,
            'x-help': '''# Graphics & Visualization

Configure graphs and visualizations of optimization results.

## Graph Types

Graphs can show:
- **Battery balance**: SOC and charge/discharge schedule
- **Prices**: Consumption, production, and spot prices
- **Average consumption**: Baseline vs optimized usage

## When to Use

- Enable during testing to visualize optimization
- Useful for understanding system behavior
- Can be displayed in Home Assistant dashboard
- Disable in production if graphs not needed (saves resources)

## Tips

- Graphs saved to add-on data directory
- Use dark_background style to match HA theme
- Toggle individual elements to simplify graphs
- Graphs regenerated each optimization run
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Graphics'
        }
    )
