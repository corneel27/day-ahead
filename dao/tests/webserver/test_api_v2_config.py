"""
Tests for API v2 configuration endpoints.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Create temporary config directory and set paths."""
    # Create temporary config and secrets files
    config_path = tmp_path / "options.json"
    secrets_path = tmp_path / "secrets.json"
    
    # Monkey patch the paths in the config module
    import dao.webserver.app.api_v2.config as config_module
    monkeypatch.setattr(config_module, 'CONFIG_PATH', config_path)
    monkeypatch.setattr(config_module, 'SECRETS_PATH', secrets_path)
    
    return tmp_path


@pytest.fixture
def valid_config():
    """Valid configuration for testing (unversioned, auto-migrates to V0)."""
    return {
        "homeassistant": {
            "protocol api": "http",
            "ip adress": "homeassistant.local",
            "ip port": 8123,
            "token": "!secret ha_token"
        },
        "database da": {
            "engine": "sqlite",
            "db_path": "../data"
        },
        "database ha": {
            "engine": "sqlite",
            "database": "home-assistant_v2.db",
            "db_path": "../data"
        },
        "meteoserver-key": "!secret meteoserver-key",
        "solar": [],
        "batteries": [
            {
                "name": "Test Battery",
                "capacity": 10.0,
                "max discharge power": 5.0,
                "max charge power": 5.0,
                "min soc": 20,
                "max soc": 90
            }
        ]
    }


@pytest.fixture
def invalid_config():
    """Invalid configuration for testing validation."""
    return {
        "homeassistant": {
            "protocol api": "invalid",
            "ip adress": "homeassistant.local",
            "ip port": "not-a-number",
            "token": "!secret ha_token"
        },
        "database da": {
            "engine": "invalid_engine"
        },
        "batteries": [
            {
                "name": "",
                "capacity": -10.0,
                "max discharge power": -5.0  
            }
        ]
    }


class TestGetConfig:
    """Test GET /api/v2/config endpoint."""
    
    def test_get_config_success(self, client, temp_config_dir, valid_config):
        """Test loading configuration successfully."""
        # Write valid config to temp file
        config_path = temp_config_dir / "options.json"
        with open(config_path, 'w') as f:
            json.dump(valid_config, f)
        
        # Send GET request
        response = client.get('/api/v2/config')
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        # After migration to V0, config_version is in the data
        # Check homeassistant field exists
        assert 'homeassistant' in data
        assert len(data.get('batteries', [])) == 1
    
    def test_get_config_file_not_found(self, client, temp_config_dir):
        """Test loading configuration when file doesn't exist."""
        # Don't create config file
        response = client.get('/api/v2/config')
        
        # Verify 404 response
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 404
    
    def test_get_config_preserves_secret_refs(self, client, temp_config_dir, valid_config):
        """Test that !secret references are NOT resolved."""
        # Write config with secret references
        config_path = temp_config_dir / "options.json"
        with open(config_path, 'w') as f:
            json.dump(valid_config, f)
        
        # Get config
        response = client.get('/api/v2/config')
        data = json.loads(response.data)
        
        # Verify secret references are intact (field name is 'hasstoken' in V0)
        assert 'homeassistant' in data
        ha_token_field = data['homeassistant'].get('hasstoken') or data['homeassistant'].get('token')
        assert ha_token_field and '!secret' in ha_token_field


class TestPostConfig:
    """Test POST /api/v2/config endpoint."""
    
    def test_post_config_success(self, client, temp_config_dir, valid_config):
        """Test saving valid configuration."""
        # Create empty config file first (ConfigurationLoader expects it to exist)
        config_path = temp_config_dir / "options.json"
        config_path.write_text('{}')
        
        # Send POST request
        response = client.post(
            '/api/v2/config',
            data=json.dumps(valid_config),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['message'] == 'Configuration saved successfully'
        assert data['status'] == 200
        
        # Verify file was written
        with open(config_path, 'r') as f:
            saved_config = json.load(f)
        assert 'config_version' in saved_config
        assert saved_config['config_version'] == 0 
        assert 'homeassistant' in saved_config
    
    def test_post_config_validation_error(self, client, temp_config_dir, invalid_config):
        """Test saving invalid configuration returns validation error."""
        # Create empty config file
        config_path = temp_config_dir / "options.json"
        config_path.write_text('{}')
        
        # Send POST request with invalid config
        response = client.post(
            '/api/v2/config',
            data=json.dumps(invalid_config),
            content_type='application/json'
        )
        
        # Verify 400 response with validation errors
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 400
        assert 'details' in data
        assert len(data['details']) > 0  # Should have error details
    
    def test_post_config_no_data(self, client, temp_config_dir):
        """Test saving with no data returns error."""
        # Send POST request without data
        response = client.post(
            '/api/v2/config',
            data='',
            content_type='application/json'
        )
        
        # Verify 400 response
        assert response.status_code == 400
        # Flask may return empty body for 400 with no JSON, so check status is enough
    
    def test_post_config_preserves_secret_refs(self, client, temp_config_dir, valid_config):
        """Test that !secret references are preserved when saving."""
        # Create empty config file
        config_path = temp_config_dir / "options.json"
        config_path.write_text('{}')
        
        # Save config with secret references
        response = client.post(
            '/api/v2/config',
            data=json.dumps(valid_config),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Read back from file
        with open(config_path, 'r') as f:
            saved_config = json.load(f)
        
        # Verify secret references are preserved (field name is 'hasstoken' in V0)
        assert 'homeassistant' in saved_config
        ha_token_field = saved_config['homeassistant'].get('hasstoken') or saved_config['homeassistant'].get('token')
        assert ha_token_field and '!secret' in ha_token_field
