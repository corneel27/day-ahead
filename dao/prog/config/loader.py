"""
Configuration loader with support for versioning, migration, and unknown key preservation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Type
from pydantic import BaseModel
import fcntl
from .migrations.migrator import migrate_config
from .versions.v0 import ConfigurationV0
# Uncomment when creating v1:
# from .versions.v1 import ConfigurationV1

logger = logging.getLogger(__name__)

# Version models registry: maps version number -> Pydantic model class
VERSION_MODELS: dict[int, Type[BaseModel]] = {
    0: ConfigurationV0,
    # Uncomment when creating v1:
    # 1: ConfigurationV1,
}

# Derive current version from registry
CURRENT_VERSION = max(VERSION_MODELS.keys())

class ConfigurationLoader:
    """
    Loads and saves configuration files with migration and unknown key preservation.
    
    Features:
    - Automatic version detection and migration
    - Unknown key preservation (extra='allow')
    - Secret resolution from separate secrets.json
    - Backup creation before migration
    """
    
    def __init__(self, config_path: Path, secrets_path: Optional[Path] = None):
        """
        Initialize the configuration loader.
        
        Args:
            config_path: Path to options.json
            secrets_path: Path to secrets.json (optional, auto-detected if omitted)
        """
        self.config_path = config_path
        self.secrets_path = secrets_path or config_path.parent / "secrets.json"
        self._raw_options: Optional[dict[str, Any]] = None
        self._secrets: Optional[dict[str, str]] = None
    
    def load_raw(self) -> dict[str, Any]:
        """
        Load raw configuration without validation.
        
        Returns:
            Raw configuration dictionary
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded configuration from {self.config_path}")
        return data
    
    def load_secrets(self) -> dict[str, str]:
        """
        Load secrets from secrets.json.
        
        Returns:
            Dictionary of secret key->value pairs
        """
        if self._secrets is not None:
            return self._secrets
        
        if not self.secrets_path.exists():
            logger.warning("No secrets file found, secret resolution will fail")
            self._secrets = {}
            return self._secrets
        
        with open(self.secrets_path, 'r', encoding='utf-8') as f:
            self._secrets = json.load(f)
        
        logger.info(f"Loaded {len(self._secrets)} secrets from {self.secrets_path}")
        return self._secrets
    
    def _load_and_migrate(self) -> dict[str, Any]:
        """
        Load configuration and apply migrations if needed.
        
        Returns:
            Migrated configuration (not yet validated with Pydantic)
        """
        with open(self.config_path, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            
            # Load raw config
            config_data = json.load(f)
            
            # Store original for unknown key preservation
            self._raw_options = config_data.copy()
            
            # Check if migration needed
            config_version = config_data.get("config_version")

            if config_version is None or config_version < CURRENT_VERSION:
                from_ver = "unversioned" if config_version is None else f"v{config_version}"
                logger.info(f"Configuration needs migration from {from_ver} to v{CURRENT_VERSION}")
                
                # Save backup before migration
                backup_path = self.config_path.parent / f"options_{from_ver}.json"
                self.save(config_data, save_path=backup_path)
                
                migrated_data = migrate_config(config_data, target_version=CURRENT_VERSION)
                
                # Update raw options with migrated version
                self._raw_options = migrated_data.copy()
                
                # Save migrated config back to disk
                f.seek(0)
                f.truncate(0)
                json.dump(migrated_data, f, indent=2, ensure_ascii=False)
                f.flush()
                logger.info(f"Saved migrated configuration to {self.config_path}")
            else:
                logger.debug("Configuration is up to date, no migration needed")
                migrated_data = config_data
            
            return migrated_data
    
    def load_and_validate(self) -> BaseModel:
        """
        Load configuration, apply migrations, and validate with Pydantic.
        
        This is the recommended way to load configuration - it automatically:
        1. Detects the current version
        2. Migrates to CURRENT_VERSION if needed
        3. Validates with the appropriate Pydantic model
        
        Returns:
            Validated Pydantic model (type depends on CURRENT_VERSION)
        """
        # Migrate to current version if required
        migrated_data = self._load_and_migrate()
        
        # Ensure secrets are loaded and available via self.secrets
        self.load_secrets()
        
        # Get the model class for current version
        version = migrated_data.get("config_version", CURRENT_VERSION)
        
        if version not in VERSION_MODELS:
            raise RuntimeError(
                f"No Pydantic model defined for version {version}. "
                f"Available versions: {list(VERSION_MODELS.keys())}"
            )
        
        model_class = VERSION_MODELS[version]
        logger.info(f"Validating configuration with {model_class.__name__}")
        
        # Validate and return
        return model_class(**migrated_data)
    
    def save(self, config_data: dict[str, Any], save_path: Optional[Path] = None) -> None:
        """
        Save configuration to disk, preserving unknown keys.
        
        Args:
            config_data: Configuration to save (can be Pydantic model dict or raw dict)
            save_path: Path to save to (defaults to self.config_path)
        """
        if save_path is None:
            save_path = self.config_path
        
        # Merge with raw options to preserve unknown keys
        if self._raw_options:
            # Start with raw options (includes unknown keys)
            merged = self._raw_options.copy()
            # Update with new values
            merged.update(config_data)
            save_data = merged
        else:
            save_data = config_data
        
        # Write to disk
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved configuration to {save_path}")
    
    @property
    def secrets(self) -> dict[str, str]:
        """Get loaded secrets (lazy load)."""
        if self._secrets is None:
            self.load_secrets()
        return self._secrets
