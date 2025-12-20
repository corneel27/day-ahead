"""
Dashboard/web UI configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class DashboardConfig(BaseModel):
    """Dashboard web UI configuration."""
    
    port: int = Field(
        default=5000,
        ge=1024, le=65535,
        description="Web UI port number",
        json_schema_extra={
            "x-help": "Port number for Day Ahead Optimizer web dashboard. Access at http://homeassistant.local:PORT. Must be between 1024-65535 (non-privileged ports).",
            "x-unit": "port",
            "x-ui-section": "Connection Settings",
            "x-validation-hint": "1024-65535, default 5000"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            'x-ui-group': 'Integration',
            'x-icon': 'view-dashboard',
            'x-order': 16,
            'x-help': '''# Dashboard Configuration

Configure web dashboard for monitoring and controlling Day Ahead Optimizer.

## Dashboard Features

- View optimization results
- Monitor device schedules
- Check price forecasts
- Review historical data
- Trigger manual optimization
- View graphs and reports

## Access

Access dashboard at:
- **Local**: http://homeassistant.local:PORT
- **IP**: http://YOUR_HA_IP:PORT

## Port Selection

- Default: 5000
- Must be unused port
- Check no conflicts with other services
- Must be >= 1024 (non-privileged)

## Tips

- Add to Home Assistant sidebar via iframe card
- Enable Ingress for secure access
- Use reverse proxy for external access
- Dashboard updates after each optimization
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Dashboard'
        }
    )
