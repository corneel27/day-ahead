"""
Migration from unversioned configuration to version 0.

Changes:
- Adds config_version field
- Migrates scheduler from dict format to array format
- Migrates vat field to vat_consumption and vat_production
- Sets database engines to mysql (old default) if not specified
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_unversioned_to_v0(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate unversioned configuration to version 0.
    
    Changes:
    - Adds config_version=0 field
    - Converts scheduler from dict format to array format:
      Old: {"0435": "get_prices", "xx00": "calc_optimum"}
      New: {"active": false, "schedule": [{"time": "0435", "action": "get_prices"}, ...]}
    - Migrates vat field to vat_consumption and vat_production
    - Sets database engines to mysql (old default) if not specified
    
    Args:
        config: Unversioned configuration
        
    Returns:
        Version 0 configuration
    """
    # Create a copy to avoid modifying original
    migrated = config.copy()
    
    # Add version field
    migrated["config_version"] = 0
    logger.info("Added config_version=0 to unversioned configuration")
    
    # Migrate scheduler format
    if "scheduler" in migrated and isinstance(migrated["scheduler"], dict):
        old_scheduler = migrated["scheduler"]
        
        # Extract 'active' field if present, otherwise default to False
        active = old_scheduler.get("active", False)
        
        # Convert string "False"/"True" to boolean if needed
        if isinstance(active, str):
            active = active.lower() == "true"
        
        # Build schedule array from time->action entries
        schedule = []
        for time_pattern, action in old_scheduler.items():
            # Skip the 'active' field - it's not a schedule entry
            if time_pattern == "active":
                continue
            
            schedule.append({
                "time": time_pattern,
                "action": action
            })
        
        # Create new scheduler structure
        migrated["scheduler"] = {
            "active": active,
            "schedule": schedule
        }
        
        logger.info(f"Migrated scheduler: active={active}, {len(schedule)} schedule entries")
    
    # Migrate prices.vat to prices.vat_consumption and prices.vat_production
    if "prices" in migrated and isinstance(migrated["prices"], dict):
        prices = migrated["prices"]
        if "vat" in prices:
            vat_value = prices["vat"]
            prices.setdefault("vat consumption", vat_value)
            prices.setdefault("vat production", vat_value)
            del prices["vat"]
            logger.info(f"Migrated prices.vat: set vat consumption and vat production to {vat_value}")
    
    # Set database engines to mysql (old default) if not specified
    if "database_ha" in migrated and isinstance(migrated["database_ha"], dict) and "engine" not in migrated["database_ha"]:
        migrated["database_ha"]["engine"] = "mysql"
        logger.info("Set database_ha engine to mysql (old default)")
    
    if "database" in migrated and isinstance(migrated["database"], dict) and "engine" not in migrated["database"]:
        migrated["database"]["engine"] = "mysql"
        logger.info("Set database engine to mysql (old default)")
    
    return migrated
