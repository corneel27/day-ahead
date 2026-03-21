import pytest
from pydantic import BaseModel, ValidationError
from dao.prog.config.models.base import EntityId, FlexValue, FlexFloat, FlexInt, FlexBool, FlexStr, SecretStr


class _Model(BaseModel):
    entity: EntityId


class _OptModel(BaseModel):
    entity: EntityId | None = None


class TestEntityId:
    # --- Valid formats ---
    def test_simple_domain_object(self):
        m = _Model(entity="sensor.battery_soc")
        assert m.entity == "sensor.battery_soc"

    def test_underscores_in_object_id(self):
        assert _Model(entity="binary_sensor.grid_connected").entity == "binary_sensor.grid_connected"

    def test_domain_starts_with_underscore(self):
        # leading underscore is valid per HA convention
        assert _Model(entity="_custom.entity").entity == "_custom.entity"

    def test_digits_in_object_id(self):
        assert _Model(entity="sensor.battery_soc_1").entity == "sensor.battery_soc_1"

    def test_optional_none(self):
        assert _OptModel(entity=None).entity is None

    # --- Invalid formats ---
    def test_plain_string_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity="not_an_entity_id")

    def test_domain_starts_with_digit_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity="1sensor.value")

    def test_dot_only_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity=".")

    def test_missing_object_id_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity="sensor.")

    def test_missing_domain_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity=".object_id")

    def test_numeric_string_raises(self):
        # "0.45" must not be misidentified as an entity ID
        with pytest.raises(ValidationError):
            _Model(entity="0.45")

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            _Model(entity="")

    def test_spaces_raise(self):
        with pytest.raises(ValidationError):
            _Model(entity="sensor.some value")

    # --- JSON schema ---
    def test_schema_has_entity_picker_widget(self):
        schema = _Model.model_json_schema()
        entity_schema = schema["properties"]["entity"]
        assert entity_schema.get("x-ui-widget") == "entity-picker"

    def test_schema_type_is_string(self):
        schema = _Model.model_json_schema()
        assert schema["properties"]["entity"]["type"] == "string"


class TestFlexValue:
    def test_serialization_literal(self):
        fv = FlexFloat(value=95)
        assert fv.model_dump() == 95

    def test_serialization_entity_id(self):
        fv = FlexFloat(value="sensor.battery_soc")
        assert fv.model_dump() == "sensor.battery_soc"

    def test_deserialization_from_literal(self):
        assert FlexFloat(value=95).value == 95
        assert FlexFloat(value="sensor.test").value == "sensor.test"
        assert FlexBool(value=True).value is True

    def test_roundtrip(self):
        fv = FlexFloat(value=95)
        assert FlexFloat(value=fv.model_dump()).value == 95

    def test_resolve_literal_float(self):
        assert FlexFloat(value=95).resolve(lambda x: "dummy") == 95.0

    def test_resolve_entity_id_float(self):
        assert FlexFloat(value="sensor.test").resolve(lambda x: "42.5") == 42.5


class TestFlexInt:
    def test_resolve_literal(self):
        assert FlexInt(value=95).resolve(lambda x: "dummy") == 95

    def test_resolve_float_literal_coerces(self):
        assert FlexInt(value=1.9).resolve(lambda x: "dummy") == 1

    def test_resolve_entity_id(self):
        # HA states often come as "95.0"
        assert FlexInt(value="sensor.soc").resolve(lambda x: "95.0") == 95


class TestFlexBool:
    def test_resolve_literal_true(self):
        assert FlexBool(value=True).resolve(lambda x: "dummy") is True

    def test_resolve_literal_false(self):
        assert FlexBool(value=False).resolve(lambda x: "dummy") is False

    def test_resolve_entity_id_on(self):
        assert FlexBool(value="binary_sensor.x").resolve(lambda x: "on") is True

    def test_resolve_entity_id_off(self):
        assert FlexBool(value="binary_sensor.x").resolve(lambda x: "off") is False

    def test_resolve_entity_id_true_string(self):
        assert FlexBool(value="binary_sensor.x").resolve(lambda x: "true") is True


class TestFlexStr:
    def test_resolve_literal(self):
        assert FlexStr(value="minimize cost").resolve(lambda x: "dummy") == "minimize cost"

    def test_resolve_entity_id(self):
        assert FlexStr(value="input_select.mode").resolve(lambda x: "minimize consumption") == "minimize consumption"

    def test_resolve_numeric_literal_coerces(self):
        assert FlexStr(value=42).resolve(lambda x: "dummy") == "42"


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