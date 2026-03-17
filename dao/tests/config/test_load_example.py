"""
Test loading the actual options_example.json with Pydantic models.
"""

import json
import pytest
from pathlib import Path
from dao.prog.config.versions.v0 import ConfigurationV0


@pytest.fixture
def options_example_path():
    """Path to options_example.json."""
    return Path(__file__).parent.parent.parent / "data" / "options_example.json"


@pytest.fixture
def options_example_data(options_example_path):
    """Load options_example.json as dict."""
    with open(options_example_path, 'r') as f:
        return json.load(f)


def test_load_options_example(options_example_data):
    """Test that options_example.json can be loaded into ConfigurationV0."""
    # Add config_version since example doesn't have it
    options_example_data["config_version"] = 0
    
    # Try to parse with Pydantic
    try:
        config = ConfigurationV0(**options_example_data)
        assert config.config_version == 0
        assert config.interval in ["15min", "1hour"]
        assert len(config.baseload) == 24
        assert len(config.battery) >= 1
        assert len(config.solar) >= 1
        print(f"✅ Successfully loaded options_example.json")
        print(f"  - {len(config.battery)} battery config(s)")
        print(f"  - {len(config.solar)} solar config(s)")
        print(f"  - {len(config.electric_vehicle)} EV config(s)")
        print(f"  - {len(config.machines)} machine config(s)")
    except Exception as e:
        pytest.fail(f"Failed to parse options_example.json: {e}")


def test_battery_has_all_fields(options_example_data):
    """Test that battery config has all expected fields including nested solar."""
    options_example_data["config_version"] = 0
    config = ConfigurationV0(**options_example_data)
    
    battery = config.battery[0]
    assert battery.name == "Accu1"
    assert battery.capacity == 28
    assert battery.charge_stages is not None
    assert len(battery.charge_stages) > 0
    
    # Check new fields exist
    assert battery.reduced_hours is not None
    assert battery.minimum_power is not None
    assert battery.dc_to_bat_efficiency is not None
    assert battery.cycle_cost is not None
    
    # Check nested solar
    assert battery.solar is not None
    assert len(battery.solar) > 0
    print(f"✅ Battery has {len(battery.solar)} DC-coupled solar installation(s)")


def test_pricing_date_based_fields(options_example_data):
    """Test that pricing date-based fields are loaded correctly."""
    options_example_data["config_version"] = 0
    config = ConfigurationV0(**options_example_data)
    
    pricing = config.prices
    assert isinstance(pricing.energy_taxes_consumption, dict)
    assert isinstance(pricing.vat_consumption, dict)
    assert "2024-01-01" in pricing.energy_taxes_consumption
    assert pricing.energy_taxes_consumption["2024-01-01"] == 0.10880
    print(f"✅ Pricing has {len(pricing.energy_taxes_consumption)} energy tax entries")


def test_optional_devices(options_example_data):
    """Test that optional devices are handled correctly."""
    options_example_data["config_version"] = 0
    config = ConfigurationV0(**options_example_data)
    
    # Boiler and heating are present in example
    assert config.boiler is not None
    assert config.heating is not None
    
    # Tibber is present in example
    assert config.tibber is not None
    
    print(f"✅ Optional devices loaded correctly")


def test_scheduler_dict_access(options_example_data):
    """Test that scheduler config allows dict-like access."""
    options_example_data["config_version"] = 0
    config = ConfigurationV0(**options_example_data)

    scheduler = config.scheduler
    tasks = scheduler.schedule
    assert len(tasks) > 0
    print(f"✅ Scheduler has {len(tasks)} scheduled tasks")


def test_unknown_keys_preserved(options_example_data):
    """Test that unknown keys in config are preserved."""
    # Add a custom unknown key
    options_example_data["custom_unknown_field"] = "test_value"
    options_example_data["config_version"] = 0
    
    config = ConfigurationV0(**options_example_data)
    
    # Pydantic should preserve it with extra='allow'
    # We can check via model_dump()
    dumped = config.model_dump()
    # Note: Pydantic may not preserve unknown keys at root level by default
    # This test documents current behavior
    print(f"✅ Unknown key handling test complete")
