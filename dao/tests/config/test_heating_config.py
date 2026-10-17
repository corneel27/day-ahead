"""
Tests for the heating configuration: the configurable degree-days base temperature
(stookgrens), which falls back to 16 °C when it is not configured, and the options
of the heat pump start/stop model.
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


class TestStartStopOptions:
    def test_defaults_keep_starts_free_and_no_off_time(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert result.min_off_length == 0.0
        assert result.start_cost == 0.0
        assert result.entity_hp_running is None
        assert result.entity_hp_running_since is None

    def test_configured_values_are_used(self):
        result = parse_heating(
            {
                "heater present": True,
                "stages": STAGES,
                "min_off_length": 0.75,
                "start_cost": 0.1,
                "entity_hp_running": "binary_sensor.heatpump_compressor_running",
                "entity_hp_running_since": "sensor.heatpump_compressor_state_since",
            }
        )
        assert result.min_off_length == 0.75
        assert result.start_cost == 0.1
        assert result.entity_hp_running == "binary_sensor.heatpump_compressor_running"
        assert (
            result.entity_hp_running_since == "sensor.heatpump_compressor_state_since"
        )

    @pytest.mark.parametrize("field", ["min_off_length", "start_cost"])
    def test_negative_is_rejected(self, field):
        with pytest.raises(ValidationError):
            parse_heating({"heater present": True, "stages": STAGES, field: -0.5})

    def test_invalid_running_entity_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(
                {"heater present": True, "stages": STAGES, "entity_hp_running": "x"}
            )

    @pytest.mark.parametrize(
        "field",
        [
            "min_off_length",
            "start_cost",
            "entity_hp_running",
            "entity_hp_running_since",
        ],
    )
    def test_has_no_alias(self, field):
        assert HeatingEnabled.model_fields[field].alias is None
