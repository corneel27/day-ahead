"""
Roundtrip tests for discriminated union config models.

Verifies that parse → model_dump() → parse produces an identical result,
ensuring serialisation and re-parsing are stable for both enabled and disabled branches.
"""

from pydantic import TypeAdapter

from dao.prog.config.models.devices.boiler import BoilerConfig, BoilerEnabled, BoilerDisabled
from dao.prog.config.models.devices.heating import HeatingConfig, HeatingEnabled, HeatingDisabled


def parse_boiler(data: dict):
    return TypeAdapter(BoilerConfig).validate_python(data)


def parse_heating(data: dict):
    return TypeAdapter(HeatingConfig).validate_python(data)


BOILER_ENABLED = {
    "boiler_present": True,
    "entity_actual_temp": "sensor.boiler_temp",
    "entity_setpoint": "input_number.boiler_setpoint",
    "entity_hysterese": "input_number.boiler_hysterese",
    "cooling_rate": 1.0,
    "heating_allowed_below": 65.0,
    "switch_entity": "switch.boiler",
}

HEATING_ENABLED = {
    "heater_present": True,
    "stages": [{"max_power": 1500.0, "cop": 4.0}],
}


class TestRoundtrip:

    def test_boiler_disabled_roundtrip(self):
        original = parse_boiler({"boiler_present": False})
        roundtripped = parse_boiler(original.model_dump())
        assert roundtripped == original

    def test_boiler_enabled_roundtrip(self):
        original = parse_boiler(BOILER_ENABLED)
        roundtripped = parse_boiler(original.model_dump())
        assert roundtripped == original

    def test_heating_disabled_roundtrip(self):
        original = parse_heating({"heater_present": False})
        roundtripped = parse_heating(original.model_dump())
        assert roundtripped == original

    def test_heating_enabled_roundtrip(self):
        original = parse_heating(HEATING_ENABLED)
        roundtripped = parse_heating(original.model_dump())
        assert roundtripped == original

    def test_boiler_enabled_disable_reenable_roundtrip(self):
        # Start enabled
        enabled = parse_boiler(BOILER_ENABLED)
        # Disable: flip discriminator, other fields survive as extras
        disabled = parse_boiler({**enabled.model_dump(), "boiler_present": False})
        assert isinstance(disabled, BoilerDisabled)
        # Re-enable from the disabled dump
        reenabled = parse_boiler({**disabled.model_dump(), "boiler_present": True})
        assert isinstance(reenabled, BoilerEnabled)
        assert reenabled == enabled

    def test_heating_enabled_disable_reenable_roundtrip(self):
        original = parse_heating(HEATING_ENABLED)
        disabled = parse_heating({**original.model_dump(), "heater_present": False})
        assert isinstance(disabled, HeatingDisabled)
        reenabled = parse_heating({**disabled.model_dump(), "heater_present": True})
        assert isinstance(reenabled, HeatingEnabled)
        assert reenabled == original
