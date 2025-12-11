"""
Tibber integration configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from .base import SecretStr


class TibberConfig(BaseModel):
    """Tibber API integration configuration."""
    
    api_token: str | SecretStr = Field(
        alias="api_token",
        description="Tibber API token (can use !secret)"
    )
    api_url: Optional[str] = Field(
        default="https://api.tibber.com/v1-beta/gql",
        alias="api url",
        description="Tibber API URL"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
