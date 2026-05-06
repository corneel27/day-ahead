"""
Configuration schema version 1.

TEMPLATE: This file is commented out and serves as a template for future versions.
Uncomment and modify when you need to create a real v1 schema.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from .v0 import ConfigurationV0


class ConfigurationV1(ConfigurationV0):
    """
    Configuration schema version 1.

    Changes from v0:
    - [DESCRIBE YOUR CHANGES HERE]
    changed meteo_attemps -> meteo_attempts

    All other fields are inherited from ConfigurationV0.
    """

    config_version: Literal[1] = 1

    # Add your new or modified fields here
    # Example:
    # new_field: str = Field(description="New required field")
    meteoserver_attempts: Optional[int] = Field(
        default=2,
        alias="meteoserver-attempts",
        ge=1,
        description="Number of meteoserver fetch attempts",
        json_schema_extra={
            "x-ui-group": "DAO",
            "x-ui-section": "Weather"
        }
    )
