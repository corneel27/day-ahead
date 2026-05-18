"""
Configuration schema version 2.

TEMPLATE: This file is commented out and serves as a template for future versions.
Uncomment and modify when you need to create a real v1 schema.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from .v1 import ConfigurationV1


class ConfigurationV2(ConfigurationV1):
    """
    Configuration schema version 2.

    Changes from v0:
    - [DESCRIBE YOUR CHANGES HERE]
    - moved "entity_balance_switch" from battery to grid
    - moved "entity_grid_setpoint" from battery to grid

    Because the moved config-entries are optional the changes are made in v0.py


    All other fields are inherited from ConfigurationV0 and ConfigurationV1
    """

    config_version: Literal[1] = 2
