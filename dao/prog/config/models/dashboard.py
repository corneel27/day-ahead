"""
Dashboard/web UI configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class DashboardConfig(BaseModel):
    """Dashboard web UI configuration."""
    
    port: int = Field(
        default=5000,
        ge=1024, le=65535,
        description="Web UI port number"
    )
    
    model_config = ConfigDict(extra='allow')
