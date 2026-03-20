"""
Tests for the BoilerConfig discriminated union.

Verifies BoilerEnabled / BoilerDisabled routing with Literal[True] / Literal[False].
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from dao.prog.config.models.devices.boiler import BoilerConfig, BoilerEnabled, BoilerDisabled


def parse_boiler(data: dict):
    return TypeAdapter(BoilerConfig).validate_python(data)


ENABLED_PYTHON = {
    "boiler_present": True,
    "entity_actual_temp": "sensor.boiler_temp",
    "entity_setpoint": "input_number.boiler_setpoint",
    "entity_hysterese": "input_number.boiler_hysterese",
    "cooling_rate": 1.0,
    "heating_allowed_below": 65.0,
    "switch_entity": "switch.boiler",
}


class TestBoilerUnion:

    def test_disabled_requires_no_other_fields(self):
        result = parse_boiler({"boiler present": False})
        assert isinstance(result, BoilerDisabled)
        assert result.boiler_present is False

    def test_disabled_allows_extra_fields(self):
        result = parse_boiler({"boiler present": False, "stray key": "value"})
        assert isinstance(result, BoilerDisabled)

    def test_enabled_with_python_names(self):
        result = parse_boiler(ENABLED_PYTHON)
        assert isinstance(result, BoilerEnabled)
        assert result.entity_actual_temp == "sensor.boiler_temp"

    def test_enabled_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            parse_boiler({"boiler present": True})

    def test_routes_false_to_disabled(self):
        assert type(parse_boiler({"boiler present": False})) is BoilerDisabled

    def test_routes_true_to_enabled(self):
        assert type(parse_boiler(ENABLED_PYTHON)) is BoilerEnabled


