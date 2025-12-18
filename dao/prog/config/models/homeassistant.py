"""
Home Assistant connection configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from .base import SecretStr


class HomeAssistantConfig(BaseModel):
    """Home Assistant connection configuration."""
    
    ip_address: Optional[str] = Field(
        default=None,
        alias="host",
        description="Home Assistant IP address (auto-detected if not set)"
    )
    ip_port: Optional[int] = Field(
        default=None,
        alias="ip port",
        description="Home Assistant port (default: 8123)"
    )
    ssl: Optional[bool] = Field(
        default=None,
        description="Whether to use SSL/HTTPS"
    )
    hasstoken: Optional[str | SecretStr] = Field(
        default=None,
        description="Home Assistant long-lived access token (can use !secret)"
    )
    protocol_api: Optional[Literal['http', 'https']] = Field(
        default=None,
        alias="protocol api",
        description="API protocol"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
