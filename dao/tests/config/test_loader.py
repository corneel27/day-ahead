"""
Tests for configuration loader.
"""

import json
import pytest
from pathlib import Path
from dao.prog.config.loader import ConfigurationLoader, config_cache, file_stamp


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    return tmp_path


@pytest.fixture
def sample_unversioned_config():
    """Sample unversioned configuration."""
    return {
        "database ha": {
            "engine": "sqlite",
            "database": "test.db"
        },
        "logging level": "info",
        "custom_field": "should_be_preserved",
        "meteoserver-key": "test_api_key"
    }


@pytest.fixture
def sample_secrets():
    """Sample secrets."""
    return {
        "db_password": "secret123",
        "api_key": "key456"
    }


class TestConfigurationLoader:
    """Test configuration loader functionality."""
    
    def test_load_nonexistent_config(self, temp_config_dir):
        """Test error when config file doesn't exist."""
        config_path = temp_config_dir / "nonexistent.json"
        loader = ConfigurationLoader(config_path)
        
        with pytest.raises(FileNotFoundError):
            loader.load_and_validate()
    
    def test_load_secrets(self, temp_config_dir, sample_secrets):
        """Test loading secrets via property."""
        config_path = temp_config_dir / "options.json"
        secrets_path = temp_config_dir / "secrets.json"
        
        config_path.write_text(json.dumps({}))
        secrets_path.write_text(json.dumps(sample_secrets))
        
        loader = ConfigurationLoader(config_path, secrets_path)
        secrets = loader.secrets
        
        assert secrets == sample_secrets
    
    def test_load_secrets_file_missing(self, temp_config_dir):
        """Test loading when secrets file doesn't exist."""
        config_path = temp_config_dir / "options.json"
        secrets_path = temp_config_dir / "nonexistent_secrets.json"
        
        config_path.write_text(json.dumps({}))
        
        loader = ConfigurationLoader(config_path, secrets_path)
        secrets = loader.secrets
        
        assert secrets == {}
    
    def test_migrate_unversioned_to_v0(self, temp_config_dir, sample_unversioned_config):
        """Test migration from unversioned to v0."""
        config_path = temp_config_dir / "options.json"
        config_path.write_text(json.dumps(sample_unversioned_config))
        
        loader = ConfigurationLoader(config_path)
        loader.load_and_validate()
        
        # Config file should have been updated with a version field
        migrated = json.loads(config_path.read_text())
        assert migrated["config_version"] == 0
    
    def test_backup_creation(self, temp_config_dir, sample_unversioned_config):
        """Test backup creation before migration."""
        config_path = temp_config_dir / "options.json"
        backup_path = temp_config_dir / "options_unversioned.json"
        
        config_path.write_text(json.dumps(sample_unversioned_config))
        
        loader = ConfigurationLoader(config_path)
        loader.load_and_validate()
        
        # Backup should exist with the pre-migration version name
        assert backup_path.exists()
        
        # Backup should contain original data
        backup_data = json.loads(backup_path.read_text())
        assert backup_data == sample_unversioned_config
    
    def test_save_preserves_unknown_keys(self, temp_config_dir):
        """Test that saving preserves unknown keys."""
        config_path = temp_config_dir / "options.json"
        
        original_data = {
            "meteoserver-key": "test_api_key",
            "unknown_field": "should_be_kept",
            "config_version": 0
        }
        
        config_path.write_text(json.dumps(original_data))
        
        loader = ConfigurationLoader(config_path)
        loader.load_and_validate()
        
        # Save with only known fields
        new_data = {
            "meteoserver-key": "updated_api_key",
            "config_version": 0
        }
        
        loader.save(new_data)
        
        # Read back and check
        saved_data = json.loads(config_path.read_text())
        
        assert saved_data["meteoserver-key"] == "updated_api_key"
        assert saved_data["unknown_field"] == "should_be_kept"
        assert saved_data["config_version"] == 0


class TestConfigCache:
    """Test the process-wide configuration cache."""

    @pytest.fixture(autouse=True)
    def clean_cache(self):
        """Every test starts and ends with an empty cache."""
        config_cache.invalidate()
        yield
        config_cache.invalidate()

    @staticmethod
    def write_config(config_path: Path, logging_level: str) -> None:
        config_path.write_text(
            json.dumps(
                {
                    "config_version": 2,
                    "logging_level": logging_level,
                    "meteoserver-key": "test_api_key",
                }
            )
        )

    def test_cached_config_is_reused(self, temp_config_dir):
        """An unchanged config file is loaded only once."""
        config_path = temp_config_dir / "options.json"
        self.write_config(config_path, "info")

        config1, loader1 = config_cache.get(config_path)
        config2, loader2 = config_cache.get(config_path)

        assert config1 is config2
        assert loader1 is loader2

    def test_changed_config_is_reloaded(self, temp_config_dir):
        """A changed config file is read again, also within one process."""
        config_path = temp_config_dir / "options.json"
        self.write_config(config_path, "info")

        config1, _ = config_cache.get(config_path)
        assert config1.logging_level == "info"

        self.write_config(config_path, "debug")

        config2, _ = config_cache.get(config_path)
        assert config2 is not config1
        assert config2.logging_level == "debug"

    def test_changed_secrets_are_reloaded(self, temp_config_dir):
        """A changed secrets file invalidates the cached config as well."""
        config_path = temp_config_dir / "options.json"
        secrets_path = temp_config_dir / "secrets.json"
        self.write_config(config_path, "info")
        secrets_path.write_text(json.dumps({"api_key": "key456"}))

        config1, loader1 = config_cache.get(config_path)
        assert loader1.secrets == {"api_key": "key456"}

        secrets_path.write_text(json.dumps({"api_key": "new_key"}))

        config2, loader2 = config_cache.get(config_path)
        assert config2 is not config1
        assert loader2.secrets == {"api_key": "new_key"}

    def test_invalidate_forces_reload(self, temp_config_dir):
        """After invalidate() the config is read from disk again."""
        config_path = temp_config_dir / "options.json"
        self.write_config(config_path, "info")

        config1, _ = config_cache.get(config_path)
        config_cache.invalidate()
        config2, _ = config_cache.get(config_path)

        assert config2 is not config1
        assert config2.logging_level == config1.logging_level

    def test_other_config_file_is_loaded(self, temp_config_dir):
        """Another path is loaded, not served from the cache."""
        config_path = temp_config_dir / "options.json"
        other_path = temp_config_dir / "other_options.json"
        self.write_config(config_path, "info")
        self.write_config(other_path, "debug")

        config1, _ = config_cache.get(config_path)
        config2, _ = config_cache.get(other_path)

        assert config1.logging_level == "info"
        assert config2.logging_level == "debug"

    def test_failed_load_does_not_keep_other_config_cached(self, temp_config_dir):
        """A failing load never leaves the configuration of another file cached."""
        config_path = temp_config_dir / "options.json"
        broken_path = temp_config_dir / "broken_options.json"
        self.write_config(config_path, "info")
        broken_path.write_text("{ this is not json")

        config1, _ = config_cache.get(config_path)

        with pytest.raises(ValueError):
            config_cache.get(broken_path)

        # het eerste bestand wordt opnieuw gelezen, niet uit de cache geleverd
        config2, _ = config_cache.get(config_path)
        assert config2 is not config1
        assert config2.logging_level == "info"

    def test_file_stamp_of_missing_file(self, temp_config_dir):
        """A missing file has no stamp."""
        assert file_stamp(temp_config_dir / "nonexistent.json") is None
