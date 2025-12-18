"""
Config wrapper providing backward-compatible access to Pydantic configuration models.

This module provides a Config class that wraps ConfigurationV0 and provides:
- Backward-compatible get() method for existing config.get(["key", "nested"]) calls
- Clean attribute access (config.battery instead of config.config.battery)
- Automatic FlexValue and SecretStr resolution
- Database connection management
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from dao.prog.config.loader import ConfigurationLoader
from dao.prog.config.models.base import FlexValue, SecretStr
from dao.prog.config.versions.v0 import ConfigurationV0
from dao.prog.db_manager import DBmanagerObj


class Config:
    """
    Backward-compatible configuration wrapper for Pydantic models.
    
    Provides both modern attribute access (config.battery) and legacy
    get() method (config.get(["battery", "lower_limit"])) for seamless migration.
    """
    
    db_da: Optional[DBmanagerObj] = None
    db_ha: Optional[DBmanagerObj] = None
    
    def __init__(self, file_name: str):
        """
        Initialize configuration from options.json file.
        
        Args:
            file_name: Path to options.json file
        """
        self.file_name = file_name
        file_path = Path(file_name)
        
        # Determine the options.json path and data directory
        # If file_name points to options.json, use it directly
        # Otherwise, assume it's a directory containing options.json
        if file_path.is_file() or file_path.name == "options.json":
            options_file = file_path
            self.data_path = file_path.parent
        else:
            options_file = file_path / "options.json"
            self.data_path = file_path
        
        # Store original options dict for backward compatibility and fallback
        with open(options_file, 'r', encoding='utf-8') as f:
            self.options = json.load(f)
        
        # Load secrets for get() method compatibility
        secrets_file = self.data_path / "secrets.json"
        if secrets_file.exists():
            with open(secrets_file, 'r', encoding='utf-8') as f:
                self.secrets = json.load(f)
        else:
            self.secrets = {}
        
        # Try to load with Pydantic validation
        self._config = None
        self._pydantic_error = None
        self._using_fallback = False
        
        try:
            # Load configuration using Pydantic loader with automatic migration
            # ConfigurationLoader expects the path to options.json file, not directory
            loader = ConfigurationLoader(config_path=options_file)
            
            # Load, migrate, and validate with appropriate version model
            self._config = loader.load_and_validate()
            
        except Exception as e:
            # Store the error for debugging
            self._pydantic_error = e
            self._using_fallback = True
            
            # Print VERY LOUD warning
            self._print_fallback_warning(e)
    
    def _print_fallback_warning(self, error: Exception):
        """Print a very loud warning when falling back to legacy mode."""
        import sys
        border = "=" * 80
        print(f"\n{border}", file=sys.stderr)
        print("⚠️  WARNING: PYDANTIC CONFIGURATION VALIDATION FAILED!", file=sys.stderr)
        print(f"{border}", file=sys.stderr)
        print(f"\nFalling back to LEGACY configuration mode (dict-based).", file=sys.stderr)
        print(f"This means you're NOT getting the benefits of Pydantic validation!\n", file=sys.stderr)
        print(f"Error details:", file=sys.stderr)
        print(f"  {type(error).__name__}: {str(error)[:200]}", file=sys.stderr)
        print(f"\nConfiguration file: {self.file_name}", file=sys.stderr)
        print(f"\nPlease report this issue or fix your configuration to match the schema.", file=sys.stderr)
        print(f"For details, check the Pydantic validation error above.\n", file=sys.stderr)
        print(f"{border}\n", file=sys.stderr)
        
        # Also log it
        logging.error(
            f"Pydantic configuration validation failed, using fallback mode: {error}"
        )
    
    def __getattr__(self, name: str) -> Any:
        """
        Provide clean attribute access to configuration fields.
        
        Examples:
            config.battery -> list[BatteryConfig]
            config.prices -> PricingConfig
            config.latitude -> FlexValue[float]
        """
        if name.startswith('_'):
            # Avoid infinite recursion for private attributes
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # If using fallback mode, use dict access
        if self._using_fallback:
            # Try to get from options dict
            snake_name = name.replace(' ', '_')
            if name in self.options:
                return self.options[name]
            elif snake_name in self.options:
                return self.options[snake_name]
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # Try to get from Pydantic model first
        if hasattr(self._config, name):
            return getattr(self._config, name)
        
        # Try snake_case version (e.g., "time_zone" for "time zone")
        snake_name = name.replace(' ', '_')
        if hasattr(self._config, snake_name):
            return getattr(self._config, snake_name)
        
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    def get(
        self, keys: list, options: dict = None, default=None
    ) -> str | dict | list | None:
        """
        Legacy get() method for backward compatibility.
        
        Supports nested key access like ["graphics", "style"] and handles
        both Pydantic models and raw dictionary access.
        
        Automatically falls back to legacy dict-based behavior if Pydantic
        validation failed during initialization.
        
        Args:
            keys: List of keys for nested access (e.g., ["battery", "lower_limit"])
            options: Optional dict to search in (for recursive calls)
            default: Default value if key not found
            
        Returns:
            Configuration value, with FlexValue/SecretStr resolved if needed
        """
        # If using fallback mode OR recursive call with dict, use legacy behavior
        if self._using_fallback or options is not None:
            return self._get_from_dict(keys, options if options is not None else self.options, default)
        
        # Otherwise use Pydantic model
        return self._get_from_model(keys, default)
    
    def _get_from_model(self, keys: list, default=None) -> Any:
        """Get value from Pydantic model using key path."""
        if not keys:
            return default
        
        # Start at root configuration
        current = self._config
        
        try:
            for i, key in enumerate(keys):
                # Convert "space case" to snake_case for Pydantic field access
                field_name = key.replace(' ', '_').replace('-', '_')
                
                # Handle array access (e.g., battery[0])
                if isinstance(current, list):
                    if isinstance(key, int):
                        current = current[key]
                    else:
                        # Key is not an int but current is a list - invalid
                        return default
                    continue
                
                # Try to get attribute from Pydantic model
                if isinstance(current, BaseModel):
                    # Try exact field name first
                    if hasattr(current, field_name):
                        current = getattr(current, field_name)
                    # Try original key name
                    elif hasattr(current, key):
                        current = getattr(current, key)
                    else:
                        # Field not found
                        return default
                # Handle dict access (for date-based configs like pricing)
                elif isinstance(current, dict):
                    if key in current:
                        current = current[key]
                    else:
                        return default
                else:
                    # Can't navigate further
                    return default
                
                # Resolve FlexValue or SecretStr if this is the final key
                if i == len(keys) - 1:
                    current = self._resolve_value(current)
            
            return current
            
        except (AttributeError, KeyError, IndexError, TypeError):
            return default
    
    def _get_from_dict(self, keys: list, options: dict, default=None) -> Any:
        """Legacy dict-based get() for recursive calls (backward compatibility)."""
        if not keys:
            return default
        
        if keys[0] in options:
            result = options[keys[0]]
            
            # Handle !secret references
            if isinstance(result, str) and result.lower().startswith("!secret"):
                secret_key = result[8:].strip()
                result = self.secrets.get(secret_key, result)
            
            if isinstance(result, dict):
                if len(keys) > 1:
                    # Recurse into nested dict
                    result = self._get_from_dict(keys[1:], result, default)
                else:
                    # Resolve all values in dict
                    for key in result:
                        result[key] = self._get_from_dict([key], result, default)
        else:
            result = default
        
        return result
    
    def _resolve_value(self, value: Any) -> Any:
        """
        Resolve FlexValue and SecretStr to their actual values.
        
        For entity resolution, this would need access to Home Assistant state,
        which should be passed in at runtime by the caller.
        """
        if isinstance(value, FlexValue):
            # Return the literal value (entity resolution happens at runtime in da_base)
            return value.model_dump()
        elif isinstance(value, SecretStr):
            # Resolve secret reference
            return value.resolve(self.secrets)
        elif isinstance(value, str) and value.startswith("!secret "):
            # Handle plain string secret references (for backward compatibility)
            secret_key = value.replace("!secret ", "", 1).strip()
            return self.secrets.get(secret_key, value)
        elif isinstance(value, BaseModel):
            # Return model as dict for backward compatibility
            return value.model_dump()
        elif isinstance(value, list):
            # Resolve all items in list
            return [self._resolve_value(item) for item in value]
        else:
            return value
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value (legacy compatibility).
        
        Note: This modifies the options dict but not the Pydantic model.
        For full integration, use ConfigurationLoader.save() instead.
        """
        self.options[key] = value
    
    def get_db_da(self, check_create: bool = False) -> Optional[DBmanagerObj]:
        """
        Get Day Ahead database connection.
        
        Args:
            check_create: If True, create database if it doesn't exist
            
        Returns:
            DBmanagerObj instance or None on error
        """
        if Config.db_da is None:
            try:
                # Use fallback mode if Pydantic failed
                if self._using_fallback:
                    engine = self.get(["database da", "engine"], None, "mysql")
                    server = self.get(["database da", "server"], None, "core-mariadb")
                    port = int(self.get(["database da", "port"], None, 0))
                    
                    if engine == "sqlite":
                        db_name = self.get(["database da", "database"], None, "day_ahead.db")
                    else:
                        db_name = self.get(["database da", "database"], None, "day_ahead")
                    
                    username = self.get(["database da", "username"], None, "day_ahead")
                    password = self.get(["database da", "password"])
                    db_path = self.get(["database da", "db_path"], None, "../data")
                    time_zone = self.get(["time_zone"])
                else:
                    # Use Pydantic model
                    db_config = self._config.database_da
                    
                    # Extract values, resolving FlexValue if needed
                    engine = self._resolve_value(db_config.engine) if db_config.engine else "mysql"
                    server = self._resolve_value(db_config.server) if db_config.server else "core-mariadb"
                    port = int(self._resolve_value(db_config.port)) if db_config.port else 0
                    
                    if engine == "sqlite":
                        db_name = self._resolve_value(db_config.database) if db_config.database else "day_ahead.db"
                    else:
                        db_name = self._resolve_value(db_config.database) if db_config.database else "day_ahead"
                    
                    username = self._resolve_value(db_config.username) if db_config.username else "day_ahead"
                    password = self._resolve_value(db_config.password) if db_config.password else None
                    db_path = self._resolve_value(db_config.db_path) if db_config.db_path else "../data"
                    time_zone = self._resolve_value(self._config.time_zone) if self._config.time_zone else None
                
                if check_create:
                    import sqlalchemy_utils
                    db_url = DBmanagerObj.db_url(
                        db_dialect=engine,
                        db_name=db_name,
                        db_server=server,
                        db_user=username,
                        db_password=password,
                        db_port=port,
                        db_path=db_path,
                    )
                    if not sqlalchemy_utils.database_exists(db_url):
                        sqlalchemy_utils.create_database(db_url)
                
                Config.db_da = DBmanagerObj(
                    db_dialect=engine,
                    db_name=db_name,
                    db_server=server,
                    db_user=username,
                    db_password=password,
                    db_port=port,
                    db_path=db_path,
                    db_time_zone=time_zone,
                )
            except Exception as ex:
                logging.error(f"Check your settings for day_ahead database: {ex}")
                return None
        
        return Config.db_da
    
    def get_db_ha(self) -> Optional[DBmanagerObj]:
        """
        Get Home Assistant database connection.
        
        Returns:
            DBmanagerObj instance or None on error
        """
        if Config.db_ha is None:
            try:
                # Use fallback mode if Pydantic failed
                if self._using_fallback:
                    engine = self.get(["database ha", "engine"], None, "mysql")
                    server = self.get(["database ha", "server"], None, "core-mariadb")
                    port = int(self.get(["database ha", "port"], None, 0))
                    
                    if engine == "sqlite":
                        db_name = self.get(["database ha", "database"], None, "home-assistant_v2.db")
                    else:
                        db_name = self.get(["database ha", "database"], None, "homeassistant")
                    
                    username = self.get(["database ha", "username"], None, "homeassistant")
                    password = self.get(["database ha", "password"])
                    db_path = self.get(["database ha", "db_path"], None, "/homeassistant")
                    time_zone = self.get(["time_zone"])
                else:
                    # Use Pydantic model
                    db_config = self._config.database_ha
                    
                    # Extract values, resolving FlexValue if needed
                    engine = self._resolve_value(db_config.engine) if db_config.engine else "mysql"
                    server = self._resolve_value(db_config.server) if db_config.server else "core-mariadb"
                    port = int(self._resolve_value(db_config.port)) if db_config.port else 0
                    
                    if engine == "sqlite":
                        db_name = self._resolve_value(db_config.database) if db_config.database else "home-assistant_v2.db"
                    else:
                        db_name = self._resolve_value(db_config.database) if db_config.database else "homeassistant"
                    
                    username = self._resolve_value(db_config.username) if db_config.username else "homeassistant"
                    password = self._resolve_value(db_config.password) if db_config.password else None
                    db_path = self._resolve_value(db_config.db_path) if db_config.db_path else "/homeassistant"
                    time_zone = self._resolve_value(self._config.time_zone) if self._config.time_zone else None
                
                Config.db_ha = DBmanagerObj(
                    db_dialect=engine,
                    db_name=db_name,
                    db_server=server,
                    db_user=username,
                    db_password=password,
                    db_port=port,
                    db_path=db_path,
                    db_time_zone=time_zone,
                )
            except Exception as ex:
                logging.error(f"Check your settings for Home Assistant database: {ex}")
                return None
        
        return Config.db_ha


def get_config(file_name: str, keys: list, default=None):
    """
    Legacy helper function for backward compatibility.
    
    Args:
        file_name: Path to options.json
        keys: List of keys for nested access
        default: Default value if not found
        
    Returns:
        Configuration value
    """
    config = Config(file_name=file_name)
    return config.get(keys, None, default)
