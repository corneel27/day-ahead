"""
Tests for the heating configuration: the configurable degree-days base temperature
(stookgrens), which falls back to 16 °C when it is not configured.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from dao.prog.config.models.devices.heating import (
    HeatingConfig,
    HeatingDisabled,
    HeatingEnabled,
)

STAGES = [{"max_power": 1000, "cop": 4.0}]


def parse_heating(data: dict):
    return TypeAdapter(HeatingConfig).validate_python(data)


def heating_with(base_temperature) -> dict:
    return {
        "heater present": True,
        "stages": STAGES,
        "degree_days_base_temperature": base_temperature,
    }


class TestDegreeDaysBaseTemperature:

    def test_defaults_to_16_when_not_configured(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert isinstance(result, HeatingEnabled)
        assert result.degree_days_base_temperature == 16.0

    def test_configured_value_is_used(self):
        assert parse_heating(heating_with(18.0)).degree_days_base_temperature == 18.0
        assert parse_heating(heating_with(15.5)).degree_days_base_temperature == 15.5

    def test_has_no_alias(self):
        # A new option uses its plain field name as key in options.json; aliases are
        # only kept for older options that need a backwards-compatible key.
        field = HeatingEnabled.model_fields["degree_days_base_temperature"]
        assert field.alias is None

    def test_other_adjustment_modes_get_the_same_default(self):
        result = parse_heating({"heater present": True, "adjustment": "on/off"})
        assert result.degree_days_base_temperature == 16.0

    def test_survives_serialisation(self):
        result = parse_heating(heating_with(17.0))
        assert result.model_dump()["degree_days_base_temperature"] == 17.0

    def test_below_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with(-1.0))

    def test_above_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with(31.0))

    def test_non_numeric_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with("warm"))

    def test_disabled_heating_needs_no_base_temperature(self):
        result = parse_heating({"heater present": False})
        assert isinstance(result, HeatingDisabled)
