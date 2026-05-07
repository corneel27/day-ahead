"""
Migration from configuration v0 to v1.

TEMPLATE: This file is commented out and serves as a template for future migrations.
Uncomment and modify when you need to create a real v0→v1 migration.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_v0_to_v1(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate from v0 to v1.

    Changes in v1:
    - [DESCRIBE YOUR CHANGES HERE]
    - changed meteo_atteps -> meteo_attempts
    - changed [ev]["entity stop laden"] -> [ev]["entity_stop_charging"]

    Args:
        config: Version 0 configuration

    Returns:
        Version 1 configuration
    """
    # Create a copy to avoid modifying original
    migrated = config.copy()

    # Example: Add required field to all batteries
    # if 'battery' in migrated:
    #     for battery in migrated['battery']:
    #         if 'efficiency' not in battery:
    #             battery['efficiency'] = 0.95  # Migration default
    #             logger.info(f"Added efficiency=0.95 to battery '{battery.get('name', 'unknown')}'")

    # meteo_attempts
    value = None
    if "meteo_attemps" in migrated:
        value = migrated["meteo_attemps"]
        del migrated["meteo_attemps"]
    if "meteo attemps" in migrated:
        value = migrated["meteo attemps"]
        del migrated["meteo attemps"]
    if value:
        migrated["meteo_attempts"] = value
        logger.info("changed meteo_attemps -> meteo_attempts")

    # entity_stop_charging
    if "electric_vehicle" in migrated and isinstance(migrated["electric_vehicle"], list):
        for ev in migrated["electric_vehicle"]:
            value = None
            if "entity_stop_laden" in ev:
                value = ev["entity_stop_laden"]
                del ev["entity_stop_laden"]
            if "entity stop laden" in ev:
                value = ev["entity stop laden"]
                del ev["entity stop laden"]
            if value:
                ev["entity_stop_charging"] = value
                logger.info("changed entity_stop_laden -> entity_stop_charging")



# Update version
    migrated['config_version'] = 1

    logger.info("Migrated configuration from v0 to v1")
    return migrated
