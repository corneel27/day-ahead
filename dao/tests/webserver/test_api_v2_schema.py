"""
Tests for API v2 schema endpoints.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_schema_dir(tmp_path, monkeypatch):
    """Create temporary schema directory and set paths."""
    # Create temporary schema directory
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_path = schema_dir / "schema.json"
    uischema_path = schema_dir / "uischema.json"
    
    # Monkey patch the paths in the config module
    import dao.webserver.app.api_v2.config as config_module
    monkeypatch.setattr(config_module, 'SCHEMA_DIR', schema_dir)
    monkeypatch.setattr(config_module, 'SCHEMA_PATH', schema_path)
    monkeypatch.setattr(config_module, 'UISCHEMA_PATH', uischema_path)
    
    return schema_dir


@pytest.fixture
def sample_schema():
    """Sample JSON schema for testing."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "config_version": {
                "type": "integer",
                "const": 2
            },
            "general": {
                "type": "object",
                "properties": {
                    "time_zone": {"type": "string"},
                    "ha_url": {"type": "string"},
                    "ha_token": {"type": "string"}
                },
                "required": ["time_zone", "ha_url", "ha_token"]
            },
            "batteries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "capacity_kwh": {"type": "number"}
                    }
                }
            }
        },
        "required": ["config_version", "general", "batteries"]
    }


@pytest.fixture
def sample_uischema():
    """Sample UI schema for testing."""
    return {
        "type": "Categorization",
        "elements": [
            {
                "type": "Category",
                "label": "General",
                "elements": [
                    {
                        "type": "Control",
                        "scope": "#/properties/general/properties/time_zone"
                    }
                ]
            },
            {
                "type": "Category",
                "label": "Batteries",
                "elements": [
                    {
                        "type": "Control",
                        "scope": "#/properties/batteries"
                    }
                ]
            }
        ]
    }


class TestGetSchema:
    """Test GET /api/v2/config/schema endpoint."""
    
    def test_get_schema_success(self, client, temp_schema_dir, sample_schema):
        """Test loading schema successfully."""
        # Write schema to temp file
        schema_path = temp_schema_dir / "schema.json"
        with open(schema_path, 'w') as f:
            json.dump(sample_schema, f)
        
        # Send GET request
        response = client.get('/api/v2/config/schema')
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['$schema'] == 'http://json-schema.org/draft-07/schema#'
        assert data['type'] == 'object'
        assert 'properties' in data
        assert 'config_version' in data['properties']
        assert 'general' in data['properties']
        assert 'batteries' in data['properties']
    
    def test_get_schema_file_not_found(self, client, temp_schema_dir):
        """Test loading schema when file doesn't exist."""
        # Don't create schema file
        response = client.get('/api/v2/config/schema')
        
        # Verify 404 response
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 404
        assert 'generate schemas' in data['details'][0].lower()
    
    def test_get_schema_returns_valid_json(self, client, temp_schema_dir, sample_schema):
        """Test that returned schema is valid JSON."""
        # Write schema
        schema_path = temp_schema_dir / "schema.json"
        with open(schema_path, 'w') as f:
            json.dump(sample_schema, f)
        
        # Get schema
        response = client.get('/api/v2/config/schema')
        assert response.status_code == 200
        
        # Verify it's valid JSON
        data = json.loads(response.data)
        assert isinstance(data, dict)
        assert data == sample_schema


class TestGetUISchema:
    """Test GET /api/v2/config/uischema endpoint."""
    
    def test_get_uischema_success(self, client, temp_schema_dir, sample_uischema):
        """Test loading UI schema successfully."""
        # Write UI schema to temp file
        uischema_path = temp_schema_dir / "uischema.json"
        with open(uischema_path, 'w') as f:
            json.dump(sample_uischema, f)
        
        # Send GET request
        response = client.get('/api/v2/config/uischema')
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['type'] == 'Categorization'
        assert 'elements' in data
        assert len(data['elements']) == 2
        assert data['elements'][0]['label'] == 'General'
        assert data['elements'][1]['label'] == 'Batteries'
    
    def test_get_uischema_file_not_found(self, client, temp_schema_dir):
        """Test loading UI schema when file doesn't exist."""
        # Don't create UI schema file
        response = client.get('/api/v2/config/uischema')
        
        # Verify 404 response
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 404
        assert 'generate schemas' in data['details'][0].lower()
    
    def test_get_uischema_returns_valid_json(self, client, temp_schema_dir, sample_uischema):
        """Test that returned UI schema is valid JSON."""
        # Write UI schema
        uischema_path = temp_schema_dir / "uischema.json"
        with open(uischema_path, 'w') as f:
            json.dump(sample_uischema, f)
        
        # Get UI schema
        response = client.get('/api/v2/config/uischema')
        assert response.status_code == 200
        
        # Verify it's valid JSON
        data = json.loads(response.data)
        assert isinstance(data, dict)
        assert data == sample_uischema
    
    def test_schemas_are_independent(self, client, temp_schema_dir, sample_schema, sample_uischema):
        """Test that schema and UI schema are independent."""
        # Write both files
        schema_path = temp_schema_dir / "schema.json"
        uischema_path = temp_schema_dir / "uischema.json"
        with open(schema_path, 'w') as f:
            json.dump(sample_schema, f)
        with open(uischema_path, 'w') as f:
            json.dump(sample_uischema, f)
        
        # Get both
        schema_response = client.get('/api/v2/config/schema')
        uischema_response = client.get('/api/v2/config/uischema')
        
        # Verify both succeed
        assert schema_response.status_code == 200
        assert uischema_response.status_code == 200
        
        # Verify they're different
        schema_data = json.loads(schema_response.data)
        uischema_data = json.loads(uischema_response.data)
        assert schema_data != uischema_data
        assert '$schema' in schema_data
        assert 'Categorization' in uischema_data.get('type', '')
