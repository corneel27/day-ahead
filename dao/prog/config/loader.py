"""
Configuration loader with support for versioning, migration, and unknown key preservation.
"""

import shutil
import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional, Type
from pydantic import BaseModel, ValidationError
import fcntl
from .migrations.migrator import migrate_config
from .versions.v0 import ConfigurationV0

# Uncomment when creating v1:
from .versions.v1 import ConfigurationV1
from .versions.v2 import ConfigurationV2

logger = logging.getLogger(__name__)


class ConfigValidationError(ValueError):
    """Raised when configuration fails Pydantic validation, with a human-readable message."""

    def __init__(self, error: ValidationError) -> None:
        lines = ["Configuration validation failed:"]
        for err in error.errors():
            path = " → ".join(str(p) for p in err["loc"])
            lines.append(f"  • {path}: {err['msg']}")
        super().__init__("\n".join(lines))


# Version models registry: maps version number -> Pydantic model class
VERSION_MODELS: dict[int, Type[BaseModel]] = {
    0: ConfigurationV0,
    1: ConfigurationV1,
    # Uncomment when creating v2:
    2: ConfigurationV2,
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

    def _load_secrets(self) -> dict[str, str]:
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

        with open(self.secrets_path, "r", encoding="utf-8") as f:
            self._secrets = json.load(f)

        logger.info(f"Loaded {len(self._secrets)} secrets from {self.secrets_path}")
        return self._secrets

    def _load_and_migrate(self) -> dict[str, Any]:
        """
        Load configuration and apply migrations if needed.

        Returns:
            Migrated configuration (not yet validated with Pydantic)
        """
        with open(self.config_path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

            # Load raw config
            config_data = json.load(f)

            # Store original for unknown key preservation
            self._raw_options = config_data.copy()

            # Check if migration needed
            config_version = config_data.get("config_version")

            if config_version is None or config_version < CURRENT_VERSION:
                from_ver = (
                    "unversioned" if config_version is None else f"v{config_version}"
                )
                logger.info(
                    f"Configuration needs migration from {from_ver} to v{CURRENT_VERSION}"
                )

                # Save backup before migration
                backup_path = self.config_path.parent / f"options_{from_ver}.json"
                shutil.copy2(self.config_path, backup_path)
                logger.info(f"Saved backup configuration to {backup_path}")

                migrated_data = migrate_config(
                    config_data, target_version=CURRENT_VERSION
                )

                # Get the model class for current version
                version = migrated_data.get("config_version", CURRENT_VERSION)
                model_class = VERSION_MODELS[version]

                # Create model instance and dump to dict for saving
                model = model_class(**migrated_data)
                save_data = model.model_dump(mode="json", exclude_none=True)

                # Update raw options with dumped version
                self._raw_options = save_data.copy()

                # Save migrated config back to disk
                f.seek(0)
                f.truncate(0)
                json.dump(save_data, f, indent=2, ensure_ascii=False)
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
        self._load_secrets()

        # Get the model class for current version
        version = migrated_data.get("config_version", CURRENT_VERSION)

        if version not in VERSION_MODELS:
            raise RuntimeError(
                f"No Pydantic model defined for version {version}. "
                f"Available versions: {list(VERSION_MODELS.keys())}"
            )

        model_class = VERSION_MODELS[version]
        logger.info(f"Validating configuration with {model_class.__name__}")

        # Validate and return; wrap pydantic's ValidationError to strip the noisy
        # input_value dumps and present only field path + message to the user.
        try:
            return model_class(**migrated_data)
        except ValidationError as e:
            raise ConfigValidationError(e) from e

    def save(
        self, config_data: dict[str, Any], save_path: Optional[Path] = None
    ) -> None:
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
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved configuration to {save_path}")

    @property
    def secrets(self) -> dict[str, str]:
        """Get loaded secrets (lazy load)."""
        if self._secrets is None:
            self._load_secrets()
        return self._secrets


def file_stamp(path: Path) -> Optional[tuple[int, int]]:
    """
    Returns a change-stamp of a file: (modification time in ns, size in bytes).

    Returns None when the file does not exist (or cannot be stat-ed), so a
    missing file compares equal to a missing file and unequal to an existing one.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


class ConfigCache:
    """
    Process-wide cache of the validated configuration.

    Loading and validating options.json on every use is wasteful: the dashboard
    creates a new Report (and thus a new DaBase) for every request. Caching the
    result forever is wrong as well: a long-running process (the flask/gunicorn
    dashboard) would keep serving the settings as they were when the process was
    started, while short-living processes (calculation, prices, meteo, started by
    the scheduler) do use the changed settings. That gives inconsistent results
    between for instance the graphs and the rest-api.

    So the cached configuration is reused only as long as options.json (and
    secrets.json) are unchanged; the cache is refreshed as soon as one of them
    is written, whichever process did the writing.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config: Optional[BaseModel] = None
        self._loader: Optional[ConfigurationLoader] = None
        self._path: Optional[Path] = None
        self._stamp: Optional[tuple] = None

    @staticmethod
    def _stamp_of(loader: "ConfigurationLoader") -> tuple:
        return file_stamp(loader.config_path), file_stamp(loader.secrets_path)

    def get(self, config_path: Path) -> tuple[BaseModel, "ConfigurationLoader"]:
        """
        Returns the validated configuration and the loader that produced it,
        loading them from disk when there is no valid cached version.

        Args:
            config_path: Path to options.json

        Returns:
            Tuple of (validated configuration, loader)
        """
        with self._lock:
            path = Path(config_path).resolve()
            if self._config is not None and self._loader is not None:
                if path == self._path and (
                    self._stamp_of(self._loader) == self._stamp
                ):
                    return self._config, self._loader
                # niets van het vorige bestand laten staan: als het lezen van
                # dit bestand mislukt mag de vorige configuratie niet als die
                # van dit bestand achterblijven
                self._clear()

            loader = ConfigurationLoader(path)
            # Take the stamp before loading: a migration rewrites options.json,
            # which then correctly invalidates this (pre-migration) stamp.
            stamp = self._stamp_of(loader)
            config = loader.load_and_validate()
            self._config = config
            self._loader = loader
            self._path = path
            self._stamp = stamp
            return config, loader

    def invalidate(self) -> None:
        """Drops the cached configuration; the next get() reloads from disk."""
        with self._lock:
            self._clear()

    def _clear(self) -> None:
        self._config = None
        self._loader = None
        self._path = None
        self._stamp = None


# Process-wide cache, shared by every DaBase-object in the process
config_cache = ConfigCache()
