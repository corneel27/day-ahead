"""
Configuration migration utilities.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_config(config_data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate configuration to latest version.
    
    Args:
        config_data: Raw configuration dictionary
        
    Returns:
        Migrated configuration dictionary
    """
    current_version = config_data.get("config_version")
    
    # Handle unversioned configs (migrate to v0)
    if current_version is None:
        logger.info("Migrating unversioned configuration to v0")
        config_data = migrate_unversioned_to_v0(config_data)
        current_version = 0
    
    # Future migrations would go here:
    # if current_version == 0:
    #     config_data = migrate_v0_to_v1(config_data)
    #     current_version = 1
    
    logger.info(f"Configuration at version {current_version}")
    return config_data


def migrate_unversioned_to_v0(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate unversioned configuration to version 0.
    
    This is a no-op migration that just adds the version field.
    No configuration format changes are made.
    
    Args:
        config: Unversioned configuration
        
    Returns:
        Version 0 configuration (with config_version field added)
    """
    # Create a copy to avoid modifying original
    migrated = config.copy()
    
    # Add version field
    migrated["config_version"] = 0
    
    logger.info("Added config_version=0 to unversioned configuration")
    
    # No other changes needed - current configs become v0 as-is
    return migrated
