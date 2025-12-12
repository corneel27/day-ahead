"""
Configuration loader with support for versioning, migration, and unknown key preservation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional
from .migrations.migrator import migrate_config

logger = logging.getLogger(__name__)


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
            secrets_path: Path to secrets.json (optional)
        """
        self.config_path = config_path
        self.secrets_path = secrets_path
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
        
        if not self.secrets_path or not self.secrets_path.exists():
            logger.warning("No secrets file found, secret resolution will fail")
            self._secrets = {}
            return self._secrets
        
        with open(self.secrets_path, 'r', encoding='utf-8') as f:
            self._secrets = json.load(f)
        
        logger.info(f"Loaded {len(self._secrets)} secrets from {self.secrets_path}")
        return self._secrets
    
    def load_and_migrate(self) -> dict[str, Any]:
        """
        Load configuration and apply migrations if needed.
        
        Returns:
            Migrated configuration (not yet validated with Pydantic)
        """
        # Load raw config
        config_data = self.load_raw()
        
        # Store original for unknown key preservation
        self._raw_options = config_data.copy()
        
        # Check if migration needed
        current_version = config_data.get("config_version")
        
        if current_version is None:
            # Create backup before first migration
            self._create_backup()
            logger.info("Configuration needs migration from unversioned to v0")
        
        # Apply migrations
        migrated_data = migrate_config(config_data)
        
        # Update raw options with migrated version
        self._raw_options = migrated_data.copy()
        
        return migrated_data
    
    def save(self, config_data: dict[str, Any]) -> None:
        """
        Save configuration to disk, preserving unknown keys.
        
        Args:
            config_data: Configuration to save (can be Pydantic model dict or raw dict)
        """
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
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved configuration to {self.config_path}")
    
    def _create_backup(self) -> None:
        """Create a backup of the current configuration."""
        if not self.config_path.exists():
            return
        
        backup_path = self.config_path.with_suffix('.json.backup')
        
        # Don't overwrite existing backup
        if backup_path.exists():
            logger.info(f"Backup already exists: {backup_path}")
            return
        
        # Copy current config to backup
        import shutil
        shutil.copy2(self.config_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
    
    @property
    def secrets(self) -> dict[str, str]:
        """Get loaded secrets (lazy load)."""
        if self._secrets is None:
            self.load_secrets()
        return self._secrets
