"""
Tests for the BoilerConfig discriminated union (Option B).

Verifies BoilerEnabled / BoilerDisabled split with Literal[True] / Literal[False]:
  1. Validates correctly at runtime
  2. Generates the expected oneOf + const JSON schema
  3. Handles both alias names and Python names (populate_by_name=True)
  4. Produces a schema compatible with jsonforms.io (no dummy required fields)
"""

import json
import pytest
from pydantic import TypeAdapter, ValidationError

from dao.prog.config.models.devices.boiler import BoilerConfig, BoilerEnabled, BoilerDisabled


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_boiler(data: dict):
    return TypeAdapter(BoilerConfig).validate_python(data)


def boiler_schema(by_alias: bool = True) -> dict:
    return TypeAdapter(BoilerConfig).json_schema(by_alias=by_alias)


# ---------------------------------------------------------------------------
# Shared valid enabled payload (alias names, matching legacy config format)
# ---------------------------------------------------------------------------

ENABLED_ALIAS = {
    "boiler present": True,
    "entity actual temp.": "sensor.boiler_temp",
    "entity setpoint": "input_number.boiler_setpoint",
    "entity hysterese": "input_number.boiler_hysterese",
    "cooling rate": 1.0,
    "heating allowed below": 65.0,
    "activate service": "press",
    "activate entity": "button.boiler_heat",
}

# Python names, matching options.json on-disk format
ENABLED_PYTHON = {
    "boiler_present": True,
    "entity_actual_temp": "sensor.boiler_temp",
    "entity_setpoint": "input_number.boiler_setpoint",
    "entity_hysterese": "input_number.boiler_hysterese",
    "cooling_rate": 1.0,
    "heating_allowed_below": 65.0,
    "activate_service": "press",
    "activate_entity": "button.boiler_heat",
}


# ---------------------------------------------------------------------------
# Runtime tests
# ---------------------------------------------------------------------------

class TestRuntimeValidation:

    def test_disabled_with_only_boiler_present(self):
        """boiler_present=false should parse with no other fields."""
        result = parse_boiler({"boiler present": False})
        assert isinstance(result, BoilerDisabled)
        assert result.boiler_present is False

    def test_disabled_ignores_extra_fields(self):
        """Extra fields should be allowed and ignored when disabled."""
        result = parse_boiler({"boiler present": False, "stray key": "value"})
        assert isinstance(result, BoilerDisabled)

    def test_enabled_with_alias_names(self):
        """Alias names (legacy format) should parse correctly."""
        result = parse_boiler(ENABLED_ALIAS)
        assert isinstance(result, BoilerEnabled)
        assert result.boiler_present is True
        assert result.entity_actual_temp == "sensor.boiler_temp"
        assert result.cop == 3.0  # default

    def test_enabled_with_python_names(self):
        """Python attribute names (options.json format) should also parse correctly."""
        result = parse_boiler(ENABLED_PYTHON)
        assert isinstance(result, BoilerEnabled)
        assert result.boiler_present is True
        assert result.entity_actual_temp == "sensor.boiler_temp"

    def test_enabled_missing_required_field_raises(self):
        """boiler_present=true without required fields should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_boiler({
                "boiler present": True,
                "cooling rate": 1.0,
                "heating allowed below": 65.0,
                "activate service": "press",
                "activate entity": "button.boiler_heat",
                # missing entity_actual_temp, entity_setpoint, entity_hysterese
            })
        errors = exc_info.value.errors()
        # With discriminated union, loc is (branch_index, field_name) — check last loc element
        missing_fields = {e['loc'][-1] for e in errors if e['type'] == 'missing'}
        assert 'entity actual temp.' in missing_fields

    def test_disabled_short_circuits_required_fields(self):
        """Key assertion: disabled boiler must NOT require operational fields."""
        try:
            result = parse_boiler({"boiler present": False})
            assert isinstance(result, BoilerDisabled)
        except Exception as e:
            pytest.fail(f"BoilerDisabled raised unexpected error: {e}")

    def test_boolean_discrimination_true(self):
        """Pydantic must correctly route True to BoilerEnabled."""
        result = parse_boiler(ENABLED_ALIAS)
        assert type(result) is BoilerEnabled

    def test_boolean_discrimination_false(self):
        """Pydantic must correctly route False to BoilerDisabled."""
        result = parse_boiler({"boiler present": False})
        assert type(result) is BoilerDisabled


# ---------------------------------------------------------------------------
# JSON Schema tests
# ---------------------------------------------------------------------------

class TestJsonSchema:

    def test_schema_uses_oneof(self):
        """Top-level schema must use oneOf."""
        schema = boiler_schema()
        assert 'oneOf' in schema, f"Expected 'oneOf' in schema, got: {list(schema.keys())}"

    def test_schema_has_two_branches(self):
        schema = boiler_schema()
        assert len(schema['oneOf']) == 2

    def test_schema_disabled_branch_has_const_false(self):
        """BoilerDisabled branch must have boiler_present: const: false."""
        schema = boiler_schema()
        defs = schema.get('$defs', {})
        disabled_def = defs.get('BoilerDisabled')
        assert disabled_def is not None, f"BoilerDisabled not found in $defs. Keys: {list(defs.keys())}"
        bp = disabled_def['properties']['boiler present']
        assert bp.get('const') == False, f"Expected const: false, got: {bp}"

    def test_schema_enabled_branch_has_const_true(self):
        """BoilerEnabled branch must have boiler_present: const: true."""
        schema = boiler_schema()
        defs = schema.get('$defs', {})
        enabled_def = defs.get('BoilerEnabled')
        assert enabled_def is not None, f"BoilerEnabled not found in $defs. Keys: {list(defs.keys())}"
        bp = enabled_def['properties']['boiler present']
        assert bp.get('const') == True, f"Expected const: true, got: {bp}"

    def test_schema_enabled_branch_has_required_fields(self):
        """BoilerEnabled branch must list operational fields as required."""
        schema = boiler_schema()
        defs = schema.get('$defs', {})
        required = defs['BoilerEnabled'].get('required', [])
        # activate_entity / activate_service are optional (switch_entity is an alternative)
        # and are enforced by model_validator, not schema required
        for field in ['entity actual temp.', 'entity setpoint', 'entity hysterese',
                      'cooling rate', 'heating allowed below']:
            assert field in required, f"'{field}' not in required: {required}"

    def test_schema_disabled_branch_has_no_operational_required_fields(self):
        """BoilerDisabled branch must NOT require any operational field."""
        schema = boiler_schema()
        defs = schema.get('$defs', {})
        required = defs['BoilerDisabled'].get('required', [])
        for field in ['entity actual temp.', 'entity setpoint', 'cooling rate', 'activate entity']:
            assert field not in required, f"'{field}' unexpectedly required in BoilerDisabled"

    def test_schema_by_alias_uses_alias_names(self):
        """by_alias=True: schema property names must be aliases."""
        schema = boiler_schema(by_alias=True)
        defs = schema.get('$defs', {})
        enabled_props = defs['BoilerEnabled']['properties']
        assert 'entity actual temp.' in enabled_props
        assert 'boiler present' in enabled_props
        assert 'entity_actual_temp' not in enabled_props
        assert 'boiler_present' not in enabled_props

    def test_schema_by_python_names_uses_python_names(self):
        """by_alias=False: schema property names must be Python attribute names."""
        schema = boiler_schema(by_alias=False)
        defs = schema.get('$defs', {})
        enabled_props = defs['BoilerEnabled']['properties']
        assert 'entity_actual_temp' in enabled_props
        assert 'boiler_present' in enabled_props
        assert 'entity actual temp.' not in enabled_props

    def test_schema_output_for_inspection(self):
        """Print the full schema — not a real assertion, useful for manual review with -s."""
        schema = boiler_schema(by_alias=False)
        print("\n--- Generated JSON Schema (by Python names) ---")
        print(json.dumps(schema, indent=2))

