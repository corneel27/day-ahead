"""
Migration from configuration v0 to v1.

TEMPLATE: This file is commented out and serves as a template for future migrations.
Uncomment and modify when you need to create a real v0→v1 migration.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_v1_to_v2(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate from v1 to v2.

    Changes in v2:
    - [DESCRIBE YOUR CHANGES HERE]
    - moved "entity_balance_switch" from battery to grid
    - moved "entity_grid_setpoint" from battery to grid

    Args:
        config: Version 1 configuration

    Returns:
        Version 2 configuration
    """
    # Create a copy to avoid modifying original
    migrated = config.copy()

    # Example: Add required field to all batteries
    # if 'battery' in migrated:
    #     for battery in migrated['battery']:
    #         if 'efficiency' not in battery:
    #             battery['efficiency'] = 0.95  # Migration default
    #             logger.info(f"Added efficiency=0.95 to battery '{battery.get('name', 'unknown')}'")


    if not ('grid' in migrated):
        migrated['grid'] = {}
    if 'battery' in migrated and isinstance(migrated["battery"], list):
        # entity_balance_switch
        value = None
        for battery in migrated['battery']:
            if "entity_balance_switch" in battery:
                if value is None:
                    value = battery["entity_balance_switch"]
                    migrated["grid"]["entity_balance_switch"] = value
                    logger.info(f"Moved 'entity_balance_switch' from battery "
                                f"{battery.get('name', 'unknown')} -> grid")
                else:
                    logger.info("Removed 'entity_balance_switch' from battery "
                                f"{battery.get('name', 'unknown')}")
                del battery["entity_balance_switch"]

        # entity_grid_setpoint
        value = None
        for battery in migrated['battery']:
            if "entity_grid_setpoint" in battery:
                if value is None:
                    value = battery["entity_grid_setpoint"]
                    migrated["grid"]["entity_grid_setpoint"] = value
                    logger.info(f"Moved 'entity_grid_setpoint' from battery "
                                f"{battery.get('name', 'unknown')} -> grid")
                else:
                    logger.info("Removed 'entity_grid_setpoint' from battery "
                                f"{battery.get('name', 'unknown')}")
                del battery["entity_grid_setpoint"]

# Update version
    migrated['config_version'] = 2

    logger.info("Migrated configuration from v1 to v2")
    return migrated
