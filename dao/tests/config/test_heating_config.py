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


class TestDegreeDaysBaseTemperature:

    def test_defaults_to_16_when_not_configured(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert isinstance(result, HeatingEnabled)
        assert result.degree_days_base_temperature == 16.0

    def test_configured_via_alias(self):
        result = parse_heating(
            {
                "heater present": True,
                "stages": STAGES,
                "degree days base temperature": 18.0,
            }
        )
        assert result.degree_days_base_temperature == 18.0

    def test_configured_via_python_name(self):
        result = parse_heating(
            {
                "heater present": True,
                "stages": STAGES,
                "degree_days_base_temperature": 15.5,
            }
        )
        assert result.degree_days_base_temperature == 15.5

    def test_other_adjustment_modes_get_the_same_default(self):
        result = parse_heating({"heater present": True, "adjustment": "on/off"})
        assert result.degree_days_base_temperature == 16.0

    def test_survives_serialisation_by_alias(self):
        result = parse_heating(
            {
                "heater present": True,
                "stages": STAGES,
                "degree days base temperature": 17.0,
            }
        )
        dumped = result.model_dump(by_alias=True)
        assert dumped["degree days base temperature"] == 17.0

    def test_below_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(
                {
                    "heater present": True,
                    "stages": STAGES,
                    "degree days base temperature": -1.0,
                }
            )

    def test_above_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(
                {
                    "heater present": True,
                    "stages": STAGES,
                    "degree days base temperature": 31.0,
                }
            )

    def test_non_numeric_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(
                {
                    "heater present": True,
                    "stages": STAGES,
                    "degree days base temperature": "warm",
                }
            )

    def test_disabled_heating_needs_no_base_temperature(self):
        result = parse_heating({"heater present": False})
        assert isinstance(result, HeatingDisabled)
