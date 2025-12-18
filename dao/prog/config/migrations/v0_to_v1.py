"""
Migration from configuration v0 to v1.

TEMPLATE: This file is commented out and serves as a template for future migrations.
Uncomment and modify when you need to create a real v0→v1 migration.
"""

# import logging
# from typing import Any
# 
# logger = logging.getLogger(__name__)
# 
# 
# def migrate_v0_to_v1(config: dict[str, Any]) -> dict[str, Any]:
#     """
#     Migrate from v0 to v1.
#     
#     Changes in v1:
#     - [DESCRIBE YOUR CHANGES HERE]
#     - Example: Add 'efficiency' field to battery config with default 0.95
#     
#     Args:
#         config: Version 0 configuration
#         
#     Returns:
#         Version 1 configuration
#     """
#     # Create a copy to avoid modifying original
#     migrated = config.copy()
#     
#     # Example: Add required field to all batteries
#     # if 'battery' in migrated:
#     #     for battery in migrated['battery']:
#     #         if 'efficiency' not in battery:
#     #             battery['efficiency'] = 0.95  # Migration default
#     #             logger.info(f"Added efficiency=0.95 to battery '{battery.get('name', 'unknown')}'")
#     
#     # Update version
#     migrated['config_version'] = 1
#     
#     logger.info("Migrated configuration from v0 to v1")
#     return migrated
