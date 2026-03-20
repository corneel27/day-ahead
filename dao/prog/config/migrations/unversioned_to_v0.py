"""
Migration from unversioned configuration to version 0.

Changes:
- Adds config_version field
- Migrates scheduler from dict format to array format
- Migrates vat field to vat_consumption and vat_production
- Sets database engines to mysql (old default) if not specified
- Coerces boiler_present / heater_present from string to boolean
"""

import logging
from typing import Any
from pydantic import TypeAdapter

_bool_adapter = TypeAdapter(bool)

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
        
        # Extract 'active' field if present, otherwise default to True
        active = old_scheduler.get("active", True)
        
        # Convert to boolean using Pydantic's lax coercion if needed
        if not isinstance(active, bool):
            try:
                active = _bool_adapter.validate_python(active)
            except Exception:
                logger.warning(f"Could not coerce scheduler.active value {active!r} to boolean, defaulting to True")
                active = True
        
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
    if "database ha" in migrated and isinstance(migrated["database ha"], dict) and "engine" not in migrated["database ha"]:
        migrated["database ha"]["engine"] = "mysql"
        logger.info("Set database ha engine to mysql (old default)")
    
    if "database da" in migrated and isinstance(migrated["database da"], dict) and "engine" not in migrated["database da"]:
        migrated["database da"]["engine"] = "mysql"
        logger.info("Set database da engine to mysql (old default)")

    # Coerce boiler_present and heater_present to boolean.
    # Old configs may have stored these as strings ("True"/"False", "yes"/"no", etc.).
    # The discriminated union requires actual booleans for routing, so we normalise here
    # using Pydantic's own lax coercion to catch all supported input formats.
    for section, field in [("boiler", "boiler_present"), ("boiler", "boiler present"),
                            ("heating", "heater_present"), ("heating", "heater present")]:
        if section in migrated and isinstance(migrated[section], dict):
            val = migrated[section].get(field)
            if not isinstance(val, bool) and val is not None:
                try:
                    migrated[section][field] = _bool_adapter.validate_python(val)
                    logger.info(f"Coerced {section}.{field} from {val!r} to boolean")
                except Exception:
                    logger.warning(f"Could not coerce {section}.{field} value {val!r} to boolean, leaving as-is")

    return migrated
