"""
Migration from unversioned configuration to version 0.

This is a no-op migration that just adds the config_version field.
No configuration format changes are made - all existing configs become v0 as-is.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
