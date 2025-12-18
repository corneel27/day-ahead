"""
Configuration migration utilities.

This module provides the main migrate_config function that orchestrates
the migration process by calling individual migration functions from the
MIGRATIONS registry.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_config(config_data: dict[str, Any], target_version: int) -> dict[str, Any]:
    """
    Migrate configuration to target version.
    
    Args:
        config_data: Raw configuration dictionary
        target_version: Target version to migrate to
        
    Returns:
        Migrated configuration dictionary
    """
    current_version = config_data.get("config_version")
    
    # Import MIGRATIONS here to avoid circular imports
    from . import MIGRATIONS
    
    # Handle unversioned configs (use special -1 version marker)
    if current_version is None:
        logger.info("Migrating unversioned configuration to v0")
        migration_key = (-1, 0)
        if migration_key in MIGRATIONS:
            config_data = MIGRATIONS[migration_key](config_data)
            current_version = 0
        else:
            raise RuntimeError("No migration defined for unversioned → v0")
    
    # Apply chain of migrations from current_version to target_version
    while current_version < target_version:
        next_version = current_version + 1
        migration_key = (current_version, next_version)
        
        if migration_key not in MIGRATIONS:
            logger.warning(
                f"No migration found for v{current_version} → v{next_version}. "
                f"Skipping to version {next_version}."
            )
            # Just update version number if no migration defined
            config_data["config_version"] = next_version
        else:
            logger.info(f"Migrating from v{current_version} to v{next_version}")
            migration_func = MIGRATIONS[migration_key]
            config_data = migration_func(config_data)
        
        current_version = next_version
    
    logger.info(f"Configuration at version {current_version}")
    return config_data
