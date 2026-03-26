"""
Migration from unversioned configuration to version 0.

Changes:
- Adds config_version field
- Migrates scheduler from dict format to array format
- Migrates vat field to vat_consumption and vat_production
- Sets database engines to mysql (old default) if not specified
- Coerces boiler_present / heater_present from string to boolean
- Migrates 'entity stop victron' to 'entity stop inverter' in battery configs
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

    # Migrate 'entity stop victron' → 'entity stop inverter' in battery configs.
    # If both are set, 'entity stop inverter' wins and 'entity stop victron' is dropped.
    if "battery" in migrated and isinstance(migrated["battery"], list):
        for battery in migrated["battery"]:
            if isinstance(battery, dict) and "entity stop victron" in battery:
                name = battery.get("name", "unknown")
                if not battery.get("entity stop inverter"):
                    battery["entity stop inverter"] = battery["entity stop victron"]
                    logger.info(
                        f"Migrated 'entity stop victron' to 'entity stop inverter' "
                        f"for battery '{name}'"
                    )
                else:
                    logger.info(
                        f"Removed deprecated 'entity stop victron' for battery '{name}' "
                        f"(already has 'entity stop inverter')"
                    )
                del battery["entity stop victron"]

    # Migrate deprecated graphics key names.
    # Old names: 'prices delivery', 'prices redelivery', 'average delivery'
    # New names: 'prices consumption', 'prices production', 'average consumption'
    _graphics_renames = {
        "prices delivery": "prices consumption",
        "prices redelivery": "prices production",
        "average delivery": "average consumption",
    }
    if "graphics" in migrated and isinstance(migrated["graphics"], dict):
        graphics = migrated["graphics"]
        for old_key, new_key in _graphics_renames.items():
            if old_key in graphics:
                graphics.setdefault(new_key, graphics[old_key])
                del graphics[old_key]
                logger.info(f"Migrated graphics.'{old_key}' to graphics.'{new_key}'")

    # Normalize solar orientation from [0, 360] to [-180, 180].
    # The solar radiation model uses 0=south, negative=east, positive=west.
    # Some configs (or UIs) use a 0-360 compass convention; values > 180 are
    # equivalent to negative azimuths: 270° east == -90°.
    def _normalize_orientation(solar_obj: dict, context: str) -> None:
        for key in ("orientation",):
            if key in solar_obj and isinstance(solar_obj[key], (int, float)):
                val = solar_obj[key]
                if val > 180:
                    solar_obj[key] = val - 360
                    logger.info(
                        f"Normalized {context}.orientation from {val} to {solar_obj[key]}"
                    )

    for i, solar in enumerate(migrated.get("solar", []) or []):
        if not isinstance(solar, dict):
            continue
        _normalize_orientation(solar, f"solar[{i}]")
        for j, string in enumerate(solar.get("strings", []) or []):
            if isinstance(string, dict):
                _normalize_orientation(string, f"solar[{i}].strings[{j}]")

    for b, battery in enumerate(migrated.get("battery", []) or []):
        if not isinstance(battery, dict):
            continue
        for i, solar in enumerate(battery.get("solar", []) or []):
            if not isinstance(solar, dict):
                continue
            _normalize_orientation(solar, f"battery[{b}].solar[{i}]")
            for j, string in enumerate(solar.get("strings", []) or []):
                if isinstance(string, dict):
                    _normalize_orientation(string, f"battery[{b}].solar[{i}].strings[{j}]")

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
                    logger.warning(f"Could not coerce {section}.{field} value {val!r} to boolean, defaulting to False")
                    migrated[section][field] = False

    return migrated
