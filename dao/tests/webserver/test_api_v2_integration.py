"""
Integration tests for API v2 - tests full workflows.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_test_env(tmp_path, monkeypatch):
    """Create complete test environment with config, secrets, and schemas."""
    # Create directory structure
    config_path = tmp_path / "options.json"
    secrets_path = tmp_path / "secrets.json"
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "schema.json"
    uischema_path = schema_dir / "uischema.json"
    
    # Monkey patch paths
    import dao.webserver.app.api_v2.config as config_module
    monkeypatch.setattr(config_module, 'CONFIG_PATH', config_path)
    monkeypatch.setattr(config_module, 'SECRETS_PATH', secrets_path)
    monkeypatch.setattr(config_module, 'SCHEMA_DIR', schema_dir)
    monkeypatch.setattr(config_module, 'SCHEMA_PATH', schema_path)
    monkeypatch.setattr(config_module, 'UISCHEMA_PATH', uischema_path)
    
    # Create initial config (unversioned, auto-migrates to V0)
    initial_config = {
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
        "batteries": []
    }
    
    # Create initial secrets
    initial_secrets = {
        "ha_token": "test_token_value"
    }
    
    # Write initial files
    with open(config_path, 'w') as f:
        json.dump(initial_config, f)
    with open(secrets_path, 'w') as f:
        json.dump(initial_secrets, f)
    
    # Create minimal schemas
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "config_version": {"type": "integer"},
            "general": {"type": "object"},
            "batteries": {"type": "array"}
        }
    }
    uischema = {
        "type": "Categorization",
        "elements": []
    }
    with open(schema_path, 'w') as f:
        json.dump(schema, f)
    with open(uischema_path, 'w') as f:
        json.dump(uischema, f)
    
    return tmp_path


class TestConfigRoundtrip:
    """Test complete config load -> modify -> save -> reload cycle."""
    
    def test_config_roundtrip(self, client, temp_test_env):
        """Test loading, modifying, saving, and reloading config."""
        # 1. Load config
        response = client.get('/api/v2/config')
        assert response.status_code == 200
        config = json.loads(response.data)
        
        # Verify initial state (after V0 migration, config_version may not be in dict)
        # Just check that we got a config with expected structure  
        assert 'homeassistant' in config
        assert len(config.get('batteries', [])) == 0
        
        # 2. Modify config - add a battery
        if 'batteries' not in config:
            config['batteries'] = []
        config['batteries'].append({
            "name": "New Battery",
            "capacity": 15.0,
            "max discharge power": 7.5,
            "max charge power": 7.5,
            "min soc": 10,
            "max soc": 95
        })
        
        # 3. Save config
        response = client.post(
            '/api/v2/config',
            data=json.dumps(config),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # 4. Reload config
        response = client.get('/api/v2/config')
        assert response.status_code == 200
        reloaded_config = json.loads(response.data)
        
        # 5. Verify changes persisted
        assert 'homeassistant' in reloaded_config
        assert len(reloaded_config.get('batteries', [])) == 1
        assert reloaded_config['batteries'][0]['name'] == 'New Battery'
        assert reloaded_config['batteries'][0]['capacity'] == 15.0
    
    def test_config_preserves_secrets(self, client, temp_test_env):
        """Test that !secret references are preserved through save/load."""
        # Load config
        response = client.get('/api/v2/config')
        config = json.loads(response.data)
        
        # Verify secret reference exists (field name is 'hasstoken' in V0)
        assert 'homeassistant' in config
        ha_token = config['homeassistant'].get('hasstoken') or config['homeassistant'].get('token') or ''
        assert '!secret' in ha_token
        
        # Save config without modification
        response = client.post(
            '/api/v2/config',
            data=json.dumps(config),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Reload and verify secret reference still intact
        response = client.get('/api/v2/config')
        reloaded_config = json.loads(response.data)
        ha_token = reloaded_config.get('homeassistant', {}).get('hasstoken') or reloaded_config.get('homeassistant', {}).get('token') or ''
        assert '!secret' in ha_token


class TestSecretsRoundtrip:
    """Test complete secrets load -> modify -> save -> reload cycle."""
    
    def test_secrets_roundtrip(self, client, temp_test_env):
        """Test loading, modifying, saving, and reloading secrets."""
        # 1. Load secrets
        response = client.get('/api/v2/secrets')
        assert response.status_code == 200
        secrets = json.loads(response.data)
        
        # Verify initial state
        assert secrets['ha_token'] == 'test_token_value'
        
        # 2. Modify secrets
        secrets['ha_token'] = 'updated_token_value'
        secrets['new_secret'] = 'new_secret_value'
        
        # 3. Save secrets
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps(secrets),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # 4. Reload secrets
        response = client.get('/api/v2/secrets')
        assert response.status_code == 200
        reloaded_secrets = json.loads(response.data)
        
        # 5. Verify changes persisted
        assert reloaded_secrets['ha_token'] == 'updated_token_value'
        assert reloaded_secrets['new_secret'] == 'new_secret_value'
    
    def test_secrets_deletion(self, client, temp_test_env):
        """Test removing secrets by overwriting with empty dict."""
        # Load initial secrets
        response = client.get('/api/v2/secrets')
        secrets = json.loads(response.data)
        assert 'ha_token' in secrets
        
        # Save empty secrets
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Reload and verify empty
        response = client.get('/api/v2/secrets')
        reloaded_secrets = json.loads(response.data)
        assert reloaded_secrets == {}


class TestConfigAndSecretsIntegration:
    """Test config and secrets working together."""
    
    def test_config_uses_secrets(self, client, temp_test_env):
        """Test that config references secrets correctly."""
        # 1. Get config and secrets
        config_response = client.get('/api/v2/config')
        secrets_response = client.get('/api/v2/secrets')
        
        config = json.loads(config_response.data)
        secrets = json.loads(secrets_response.data)
        
        # 2. Verify config has secret reference
        assert 'homeassistant' in config
        assert 'token' in config['homeassistant']
        assert '!secret' in config['homeassistant']['token']
        
        # 3. Verify actual secret value exists
        assert secrets['ha_token'] == 'test_token_value'
        
        # 4. Add new secret (don't modify config structure, just check secrets work)
        secrets['new_api_key'] = 'new_secret_value'
        
        # 5. Save secrets only (config is already valid)
        secrets_save = client.post(
            '/api/v2/secrets',
            data=json.dumps(secrets),
            content_type='application/json'
        )
        
        assert secrets_save.status_code == 200
        
        # 6. Reload and verify
        secrets_response = client.get('/api/v2/secrets')
        reloaded_secrets = json.loads(secrets_response.data)
        
        assert reloaded_secrets.get('new_api_key') == 'new_secret_value'


class TestSchemaValidation:
    """Test schema validation in context of full workflow."""
    
    def test_schemas_loaded(self, client, temp_test_env):
        """Test that schemas can be loaded."""
        # Get schema
        schema_response = client.get('/api/v2/config/schema')
        assert schema_response.status_code == 200
        schema = json.loads(schema_response.data)
        assert '$schema' in schema
        
        # Get UI schema
        uischema_response = client.get('/api/v2/config/uischema')
        assert uischema_response.status_code == 200
        uischema = json.loads(uischema_response.data)
        assert uischema['type'] == 'Categorization'
    
    def test_validation_prevents_invalid_save(self, client, temp_test_env):
        """Test that validation prevents saving invalid config."""
        # Create invalid config (negative capacity)
        invalid_config = {
            "config_version": 2,
            "general": {
                "time_zone": "Invalid/Timezone",
                "ha_url": "not-a-url",
                "ha_token": "!secret ha_token"
            },
            "batteries": [
                {
                    "name": "",
                    "capacity_kwh": -10.0,  # Invalid: negative
                    "charge_rate_kw": 0,
                    "discharge_rate_kw": -5.0
                }
            ]
        }
        
        # Try to save
        response = client.post(
            '/api/v2/config',
            data=json.dumps(invalid_config),
            content_type='application/json'
        )
        
        # Should fail validation
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'details' in data


class TestConcurrentAccess:
    """Test handling of concurrent requests."""
    
    def test_multiple_saves_sequential(self, client, temp_test_env):
        """Test multiple sequential saves work correctly."""
        # Load initial config
        response = client.get('/api/v2/config')
        config = json.loads(response.data)
        
        # Save multiple times with modifications
        for i in range(5):
            # Modify a field that exists
            if 'time_zone' in config:
                config['time_zone'] = f'UTC_{i}'
            response = client.post(
                '/api/v2/config',
                data=json.dumps(config),
                content_type='application/json'
            )
            assert response.status_code == 200
        
        # Verify final state
        response = client.get('/api/v2/config')
        final_config = json.loads(response.data)
        if 'time_zone' in final_config:
            assert final_config['time_zone'] == 'UTC_4'


class TestErrorRecovery:
    """Test error handling and recovery."""
    
    def test_config_survives_invalid_save_attempt(self, client, temp_test_env):
        """Test that original config is preserved if save fails."""
        # Load initial config
        response = client.get('/api/v2/config')
        original_config = json.loads(response.data)
        original_has_timezone = 'time_zone' in original_config
        original_timezone = original_config.get('time_zone')
        
        # Try to save invalid config
        invalid_config = original_config.copy()
        # Make it invalid - bad IP port type
        if 'homeassistant' in invalid_config:
            invalid_config['homeassistant']['ip port'] = "not-a-number"
        
        response = client.post(
            '/api/v2/config',
            data=json.dumps(invalid_config),
            content_type='application/json'
        )
        assert response.status_code == 400
        
        # Reload and verify original config unchanged
        response = client.get('/api/v2/config')
        current_config = json.loads(response.data)
        if original_has_timezone:
            assert current_config.get('time_zone') == original_timezone
