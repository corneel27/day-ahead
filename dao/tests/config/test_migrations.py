"""
Tests for configuration migrations.
"""

import pytest
from dao.prog.config.migrations.migrator import migrate_config
from dao.prog.config.migrations.unversioned_to_v0 import migrate_unversioned_to_v0
from dao.prog.config.models.pricing import PricingConfig
from dao.prog.config.models.database import HADatabaseConfig, DatabaseConfig
from dao.prog.config.models.scheduler import SchedulerConfig


def test_migrate_unversioned_to_v0():
    """Test migration from unversioned config to v0."""
    old_config = {
        "latitude": 52.0,
        "longitude": 5.0,
        "battery": [{"name": "Test", "capacity": 10}]
    }
    
    new_config = migrate_unversioned_to_v0(old_config)
    
    assert new_config["config_version"] == 0
    assert new_config["latitude"] == 52.0
    assert new_config["longitude"] == 5.0
    assert new_config["battery"][0]["name"] == "Test"


def test_migrate_unversioned_to_v0_with_vat():
    """Test migration of prices.vat to prices.vat_consumption and prices.vat_production."""
    old_config = {
        "latitude": 52.0,
        "prices": {
            "source day ahead": "nordpool",
            "energy taxes consumption": {},
            "energy taxes production": {},
            "cost supplier consumption": {},
            "cost supplier production": {},
            "last invoice": "2024-01-01",
            "vat": {"2024-01-01": 21}
        }
    }
    
    new_config = migrate_unversioned_to_v0(old_config)
    
    assert new_config["config_version"] == 0
    assert "vat" not in new_config["prices"]
    assert new_config["prices"]["vat consumption"] == {"2024-01-01": 21}
    assert new_config["prices"]["vat production"] == {"2024-01-01": 21}
    
    # Validate that PricingConfig still works with migrated prices data
    pricing = PricingConfig(**new_config["prices"])
    assert pricing.vat_consumption == {"2024-01-01": 21}
    assert pricing.vat_production == {"2024-01-01": 21}


def test_migrate_unversioned_to_v0_database_engines():
    """Test migration sets database engines to mysql if not specified."""
    old_config = {
        "latitude": 52.0,
        "database ha": {"password": "secret"},
        "database da": {"password": "secret"}
    }
    
    new_config = migrate_unversioned_to_v0(old_config)
    
    assert new_config["config_version"] == 0
    assert new_config["database ha"]["engine"] == "mysql"
    assert new_config["database da"]["engine"] == "mysql"

    # Validate that database models still work with migrated data
    ha_db = HADatabaseConfig(**new_config["database ha"])
    assert ha_db.engine == "mysql"
    assert ha_db.username == "homeassistant"
    da_db = DatabaseConfig(**new_config["database da"])
    assert da_db.engine == "mysql"
    assert da_db.username == "day_ahead"



def test_migrate_unversioned_to_v0_scheduler():
    """Test migration of scheduler from dict format to array format."""
    old_config = {
        "scheduler": {
            "active": "True",
            "0435": "get_day_ahead_prices",
            "0445": "get_meteo_data",
            "0500": "calc_optimum",
        }
    }

    new_config = migrate_unversioned_to_v0(old_config)

    assert new_config["config_version"] == 0
    assert new_config["scheduler"]["active"] is True
    assert len(new_config["scheduler"]["schedule"]) == 3

    # Validate that SchedulerConfig still works with migrated data
    scheduler = SchedulerConfig(**new_config["scheduler"])
    assert scheduler.active is True
    assert len(scheduler.schedule) == 3
    assert scheduler.schedule[0].time == "0435"
    assert scheduler.schedule[0].action == "get_day_ahead_prices"


def test_migrate_config_with_target_version():
    """Test migrate_config with explicit target version."""
    config = {
        "latitude": 52.0,
        "longitude": 5.0,
    }
    
    # Migrate to v0 (adds version field)
    migrated = migrate_config(config, target_version=0)
    
    assert migrated["config_version"] == 0
    assert migrated["latitude"] == 52.0


def test_migrate_config_already_at_target():
    """Test that migration is no-op when already at target version."""
    config = {
        "config_version": 0,
        "latitude": 52.0,
    }
    
    migrated = migrate_config(config, target_version=0)
    
    assert migrated["config_version"] == 0
    assert migrated["latitude"] == 52.0


# Example test for future v0→v1 migration (uncomment when implementing):
# def test_v0_to_v1_adds_efficiency():
#     """Test v0→v1 migration adds efficiency to batteries."""
#     old_config = {
#         "config_version": 0,
#         "battery": [{"name": "Test", "capacity": 10, "max_charge_power": 5}]
#     }
#     
#     from dao.prog.config.migrations.v0_to_v1 import migrate_v0_to_v1
#     new_config = migrate_v0_to_v1(old_config)
#     
#     assert new_config['config_version'] == 1
#     assert new_config['battery'][0]['efficiency'] == 0.95
#
#
# def test_migrate_v0_to_v1_via_migrate_config():
#     """Test full migration chain from v0 to v1 using migrate_config."""
#     old_config = {
#         "config_version": 0,
#         "battery": [{"name": "Test", "capacity": 10, "max_charge_power": 5}]
#     }
#     
#     migrated = migrate_config(old_config, target_version=1)
#     
#     assert migrated['config_version'] == 1
#     assert migrated['battery'][0]['efficiency'] == 0.95
