"""
Tests for base configuration models (FlexValue, SecretStr).
"""

import pytest
from dao.prog.config.models.base import FlexValue, SecretStr


class TestFlexValue:
    """Test FlexValue for flexible settings (literals or HA entities)."""
    
    def test_literal_integer(self):
        """Test literal integer value."""
        flex = FlexValue(value=95)
        assert flex.value == 95
        assert not FlexValue.is_entity_id(flex.value)
    
    def test_literal_float(self):
        """Test literal float value."""
        flex = FlexValue(value=23.5)
        assert flex.value == 23.5
        assert not FlexValue.is_entity_id(flex.value)
    
    def test_literal_bool(self):
        """Test literal boolean value."""
        flex = FlexValue(value=True)
        assert flex.value is True
        assert not FlexValue.is_entity_id(flex.value)
    
    def test_entity_id_detection(self):
        """Test entity ID detection."""
        flex = FlexValue(value="sensor.battery_soc")
        assert flex.value == "sensor.battery_soc"
        assert FlexValue.is_entity_id(flex.value)
    
    def test_resolve_literal(self):
        """Test resolving literal value."""
        flex = FlexValue(value=42)
        
        # Mock HA state getter (won't be called for literals)
        def mock_getter(entity_id):
            raise AssertionError("Should not be called for literals")
        
        result = flex.resolve(mock_getter, target_type=int)
        assert result == 42
    
    def test_resolve_entity_int(self):
        """Test resolving entity ID to int."""
        flex = FlexValue(value="sensor.battery_soc")
        
        # Mock HA state getter
        def mock_getter(entity_id):
            assert entity_id == "sensor.battery_soc"
            return "95.0"  # HA returns strings
        
        result = flex.resolve(mock_getter, target_type=int)
        assert result == 95
        assert isinstance(result, int)
    
    def test_resolve_entity_bool(self):
        """Test resolving entity ID to bool."""
        flex = FlexValue(value="binary_sensor.grid_connected")
        
        def mock_getter(entity_id):
            return "on"
        
        result = flex.resolve(mock_getter, target_type=bool)
        assert result is True
    
    def test_resolve_entity_float(self):
        """Test resolving entity ID to float."""
        flex = FlexValue(value="sensor.temperature")
        
        def mock_getter(entity_id):
            return "23.7"
        
        result = flex.resolve(mock_getter, target_type=float)
        assert result == 23.7
        assert isinstance(result, float)


class TestSecretStr:
    """Test SecretStr for secret reference handling."""
    
    def test_parse_secret_reference(self):
        """Test parsing !secret syntax."""
        secret = SecretStr.model_validate("!secret db_password")
        assert secret.secret_key == "db_password"
    
    def test_direct_secret_key(self):
        """Test direct secret key (already parsed)."""
        secret = SecretStr(secret_key="db_password")
        assert secret.secret_key == "db_password"
    
    def test_resolve_secret(self):
        """Test resolving secret from secrets dict."""
        secret = SecretStr(secret_key="db_password")
        secrets = {"db_password": "super_secret_123"}
        
        result = secret.resolve(secrets)
        assert result == "super_secret_123"
    
    def test_resolve_secret_not_found(self):
        """Test that a missing key is returned as a literal plain-text value."""
        secret = SecretStr(secret_key="missing_key")
        secrets = {"other_key": "value"}
        
        result = secret.resolve(secrets)
        assert result == "missing_key"
