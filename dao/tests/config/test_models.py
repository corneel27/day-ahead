import pytest
from dao.prog.config.models.base import FlexValue, SecretStr


class TestFlexValue:
    def test_serialization_literal(self):
        """Test that FlexValue serializes literals correctly."""
        fv = FlexValue(value=95)
        serialized = fv.model_dump()
        assert serialized == 95

        # Test round-trip
        deserialized = FlexValue(value=serialized)
        assert deserialized.value == 95

    def test_serialization_entity_id(self):
        """Test that FlexValue serializes entity IDs correctly."""
        fv = FlexValue(value="sensor.battery_soc")
        serialized = fv.model_dump()
        assert serialized == "sensor.battery_soc"

        # Test round-trip
        deserialized = FlexValue(value=serialized)
        assert deserialized.value == "sensor.battery_soc"

    def test_deserialization_from_literal(self):
        """Test that FlexValue can be deserialized from bare literals."""
        fv = FlexValue(value=95)
        assert fv.value == 95

        fv_str = FlexValue(value="sensor.test")
        assert fv_str.value == "sensor.test"

        fv_bool = FlexValue(value=True)
        assert fv_bool.value is True

    def test_serialization_vs_deserialization_format(self):
        """Test that serialized format is flat, different from internal dict."""
        # Input: value
        fv = FlexValue(value=95)
        # Serialized: flat value
        serialized = fv.model_dump()
        assert serialized == 95

        # Deserialization accepts the flat value
        fv_from_flat = FlexValue(value=serialized)
        assert fv_from_flat.value == 95

    def test_resolve_literal(self):
        """Test resolving literal values."""
        fv = FlexValue(value=95)
        result = fv.resolve(lambda x: "dummy", target_type=int)
        assert result == 95

    def test_resolve_entity_id(self):
        """Test resolving entity IDs."""
        fv = FlexValue(value="sensor.test")
        result = fv.resolve(lambda x: "42.5", target_type=float)
        assert result == 42.5


class TestSecretStr:
    def test_serialization_secret(self):
        """Test SecretStr serialization."""
        ss = SecretStr(secret_key="db_password", is_secret=True)
        serialized = ss.model_dump()
        assert serialized == "!secret db_password"

    def test_serialization_secret_json(self):
        ss = SecretStr(secret_key="db_password", is_secret=True)
        json_str = ss.model_dump_json()
        assert json_str == '"!secret db_password"'

    def test_deserialization_secret(self):
        ss = SecretStr.model_validate("!secret db_password")
        assert ss.secret_key == "db_password"
        assert ss.is_secret is True

    def test_resolve_secret(self):
        ss = SecretStr.model_validate("!secret db_password")
        secrets = {"db_password": "secret123"}
        result = ss.resolve(secrets)
        assert result == "secret123"

    def test_resolve_literal(self):
        ss = SecretStr(secret_key="plain_password")
        secrets = {}
        result = ss.resolve(secrets)
        assert result == "plain_password"