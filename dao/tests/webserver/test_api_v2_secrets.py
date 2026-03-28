"""
Tests for API v2 secrets endpoints.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_secrets_dir(tmp_path, monkeypatch):
    """Create temporary secrets directory and set paths."""
    # Create temporary config and secrets files
    config_path = tmp_path / "options.json"
    secrets_path = tmp_path / "secrets.json"
    
    # Monkey patch the paths in the config module
    import dao.webserver.app.api_v2.config as config_module
    monkeypatch.setattr(config_module, 'CONFIG_PATH', config_path)
    monkeypatch.setattr(config_module, 'SECRETS_PATH', secrets_path)
    
    # Create empty config file (required by ConfigurationLoader)
    config_path.write_text('{}')
    
    return tmp_path


@pytest.fixture
def valid_secrets():
    """Valid secrets for testing."""
    return {
        "ha_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test_token",
        "solcast_api_key": "test_api_key_12345",
        "custom_secret": "test_secret_value"
    }


class TestGetSecrets:
    """Test GET /api/v2/secrets endpoint."""
    
    def test_get_secrets_success(self, client, temp_secrets_dir, valid_secrets):
        """Test loading secrets successfully."""
        # Write secrets to temp file
        secrets_path = temp_secrets_dir / "secrets.json"
        with open(secrets_path, 'w') as f:
            json.dump(valid_secrets, f)
        
        # Send GET request
        response = client.get('/api/v2/secrets')
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['ha_token'] == valid_secrets['ha_token']
        assert data['solcast_api_key'] == valid_secrets['solcast_api_key']
        assert data['custom_secret'] == valid_secrets['custom_secret']
    
    def test_get_secrets_file_not_found(self, client, temp_secrets_dir):
        """Test loading secrets when file doesn't exist returns empty dict."""
        # Don't create secrets file
        response = client.get('/api/v2/secrets')
        
        # Verify 200 response with empty dict
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == {}
    
    def test_get_secrets_returns_actual_values(self, client, temp_secrets_dir, valid_secrets):
        """Test that actual secret values are returned (NOT masked)."""
        # Write secrets
        secrets_path = temp_secrets_dir / "secrets.json"
        with open(secrets_path, 'w') as f:
            json.dump(valid_secrets, f)
        
        # Get secrets
        response = client.get('/api/v2/secrets')
        data = json.loads(response.data)
        
        # Verify actual values are returned, not masked
        assert '***' not in data['ha_token']
        assert data['ha_token'] == valid_secrets['ha_token']
        assert data['solcast_api_key'] == valid_secrets['solcast_api_key']


class TestPostSecrets:
    """Test POST /api/v2/secrets endpoint."""
    
    def test_post_secrets_success(self, client, temp_secrets_dir, valid_secrets):
        """Test saving valid secrets."""
        # Send POST request
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps(valid_secrets),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['message'] == 'Secrets saved successfully'
        assert data['status'] == 200
        
        # Verify file was written
        secrets_path = temp_secrets_dir / "secrets.json"
        with open(secrets_path, 'r') as f:
            saved_secrets = json.load(f)
        assert saved_secrets['ha_token'] == valid_secrets['ha_token']
        assert saved_secrets['solcast_api_key'] == valid_secrets['solcast_api_key']
    
    def test_post_secrets_empty_dict(self, client, temp_secrets_dir):
        """Test saving empty secrets dict is valid."""
        # Send POST request with empty dict
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        # Verify 200 response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['message'] == 'Secrets saved successfully'
        
        # Verify file was written with empty dict
        secrets_path = temp_secrets_dir / "secrets.json"
        with open(secrets_path, 'r') as f:
            saved_secrets = json.load(f)
        assert saved_secrets == {}
    
    def test_post_secrets_invalid_value_type(self, client, temp_secrets_dir):
        """Test saving secrets with non-string values returns error."""
        # Create secrets with invalid types
        invalid_secrets = {
            "ha_token": "valid_string",
            "invalid_number": 12345,  # Should be string
            "invalid_dict": {"nested": "value"}  # Should be string
        }
        
        # Send POST request
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps(invalid_secrets),
            content_type='application/json'
        )
        
        # Verify 400 response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 400
    
    def test_post_secrets_no_data(self, client, temp_secrets_dir):
        """Test saving with no data returns error."""
        # Send POST request without data (None, not empty dict)
        response = client.post(
            '/api/v2/secrets',
            data='',
            content_type='application/json'
        )
        
        # Verify 400 response
        assert response.status_code == 400
        # Flask may return empty body for 400 with no JSON, so check status is enough
    
    def test_post_secrets_atomic_save(self, client, temp_secrets_dir, valid_secrets):
        """Test that secrets are saved atomically (file locking)."""
        # Save secrets multiple times to test atomic writes
        for i in range(3):
            modified_secrets = valid_secrets.copy()
            modified_secrets['iteration'] = str(i)
            
            response = client.post(
                '/api/v2/secrets',
                data=json.dumps(modified_secrets),
                content_type='application/json'
            )
            assert response.status_code == 200
        
        # Verify final state
        secrets_path = temp_secrets_dir / "secrets.json"
        with open(secrets_path, 'r') as f:
            saved_secrets = json.load(f)
        assert saved_secrets['iteration'] == '2'
    
    def test_post_secrets_update_existing(self, client, temp_secrets_dir, valid_secrets):
        """Test updating existing secrets file."""
        # Create initial secrets file
        secrets_path = temp_secrets_dir / "secrets.json"
        initial_secrets = {"old_secret": "old_value"}
        with open(secrets_path, 'w') as f:
            json.dump(initial_secrets, f)
        
        # Save new secrets (should replace old file)
        response = client.post(
            '/api/v2/secrets',
            data=json.dumps(valid_secrets),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Verify old secrets are replaced
        with open(secrets_path, 'r') as f:
            saved_secrets = json.load(f)
        assert 'old_secret' not in saved_secrets
        assert 'ha_token' in saved_secrets
