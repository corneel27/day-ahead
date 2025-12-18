# AI Agent Guidelines for Day Ahead Optimizer

This document provides guidelines for AI coding assistants working on the Day Ahead Optimizer (DAO) project. It covers the project architecture, coding patterns, and important considerations when making changes.

## Project Overview

**Day Ahead Optimizer** is a Home Assistant add-on that optimizes household energy consumption based on dynamic electricity pricing and weather forecasts. It uses Mixed-Integer Linear Programming (MIP) to optimize:

- Battery charge/discharge scheduling
- Electric vehicle charging
- Heat pump operation
- Boiler heating
- Other controllable appliances

**Key Technologies:**
- Python 3.12+
- Pydantic 2.10.3 for configuration validation
- Flask/Gunicorn for web dashboard
- MIP solver for optimization
- SQLite/MySQL/PostgreSQL for data storage

---

## Configuration System

### Pydantic Models

The project uses **Pydantic 2.10.3** for type-safe configuration. Key patterns:

#### 1. **FlexValue Pattern**

Some fields support both literal values AND Home Assistant entity IDs for dynamic runtime resolution:

```python
from dao.prog.config.models.base import FlexValue

# In model definition:
degree_days_factor: Union[float, FlexValue]

# Usage allows:
"degree_days_factor": 2.5                    # Literal value
"degree_days_factor": "sensor.degree_days"   # HA entity ID
```

**Fields with FlexValue support:**
- `degree_days_factor` (heating)
- `boiler_setpoint` (boiler)
- `boiler_hysterese` (boiler)
- `strategy` (optimization)
- `max_gap` (optimization)
- `optimal_low_level` (battery)
- `penalty_low_soc` (battery)

#### 2. **Required vs Optional Fields**

**CRITICAL:** Analyze actual code usage to determine if fields should be Optional:

```python
# ✅ CORRECT: Field accessed directly without None check
dc_to_bat_efficiency: float = Field(ge=0, le=1, ...)
# Code: self.battery_options[b]["dc_to_bat efficiency"]  # No None check → REQUIRED

# ✅ CORRECT: Field checked for None before use
notification_entity: Optional[str] = Field(default=None, ...)
# Code: if self.notification_entity is not None: ...  # None check → OPTIONAL
```

**To determine optionality:** Search field usage with `grep -r "field_name" dao/prog/*.py` and check for None guards.

#### 3. **Model Validators**

Use `@model_validator` for cross-field validation:

```python
from pydantic import model_validator

@model_validator(mode='after')
def validate_database_config(self) -> 'DatabaseConfig':
    """Validate engine-specific requirements."""
    if self.engine in ('mysql', 'postgresql'):
        if not self.server:
            raise ValueError(f"{self.engine} requires 'server'")
    return self
```

#### 4. **Secrets Management**

Never store secrets directly in `options.json`:

```python
# In options.json:
"password": "!secret db_password"

# In secrets.json:
{"db_password": "actual_password_here"}

# Model definition:
from dao.prog.config.models.base import SecretStr

password: SecretStr
```

---

## Common Patterns

### 1. Database Access

The project supports **MySQL/MariaDB**, **PostgreSQL**, and **SQLite**:

```python
# Configuration checked at runtime
if config.database_da.engine == "sqlite":
    # SQLite-specific code
elif config.database_da.engine in ("mysql", "postgresql"):
    # Server-based DB code
```

## Code Style and Best Practices

### 1. Type Hints

Always use type hints for function parameters and return values:

```python
def calculate_solar_production(
    capacity: float,
    irradiation: float,
    efficiency: float
) -> float:
    """Calculate solar production in kWh."""
    return capacity * irradiation * efficiency
```

### 2. Docstrings

Use docstrings for all functions, classes, and modules:

```python
def optimize_battery_schedule(
    prices: list[float],
    solar_forecast: list[float],
    battery_capacity: float
) -> dict[str, Any]:
    """
    Optimize battery charge/discharge schedule.
    
    Args:
        prices: Hourly electricity prices (€/kWh)
        solar_forecast: Solar production forecast (kWh)
        battery_capacity: Battery capacity (kWh)
        
    Returns:
        Dictionary with optimized schedule and metrics
    """
    ...
```

### 3. Error Handling

Always handle expected errors gracefully:

```python
try:
    data = fetch_weather_data()
except ConnectionError as e:
    logger.error(f"Failed to fetch weather data: {e}")
    # Use cached data or default values
    data = get_cached_weather_data()
```

---

---

## Configuration Migrations

When adding **required** fields **without defaults**, you must create a migration. Fields with defaults don't need migrations.

### When to Create a Migration

- ✅ Adding a required field WITHOUT a default value
- ✅ Changing field types in incompatible ways
- ✅ Restructuring configuration format
- ❌ Adding optional fields (no migration needed)
- ❌ Adding required fields WITH default values (no migration needed)

### Migration Process

#### Step 1: Decide if Migration is Needed

**Skip migration if your field has a default!**

```python
# ✅ NO MIGRATION NEEDED - has default
heater_present: bool = Field(default=False, ...)

# ❌ MIGRATION NEEDED - required without default
heating_stages: list[HeatingStage] = Field(min_length=1, ...)
```

#### Step 2: Create Migration File (if needed)

**Template is already provided!** See `dao/prog/config/migrations/v0_to_v1.py` for a commented template.

Uncomment and modify the template in `dao/prog/config/migrations/v0_to_v1.py`:

```python
"""Migration from configuration v0 to v1."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_v0_to_v1(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate from v0 to v1.
    
    Changes in v1:
    - Add 'efficiency' field to battery config with default 0.95
    """
    migrated = config.copy()
    
    # Add required field to all batteries
    if 'battery' in migrated:
        for battery in migrated['battery']:
            if 'efficiency' not in battery:
                battery['efficiency'] = 0.95  # Migration default
                logger.info(f"Added efficiency=0.95 to battery '{battery.get('name', 'unknown')}'")
    
    # Update version
    migrated['config_version'] = 1
    
    logger.info("Migrated configuration from v0 to v1")
    return migrated
```

#### Step 3: Register Migration

In `dao/prog/config/migrations/__init__.py`, uncomment the import and registration:

```python
from .migrator import migrate_config
from .unversioned_to_v0 import migrate_unversioned_to_v0
from .v0_to_v1 import migrate_v0_to_v1  # Uncomment this line

MIGRATIONS: dict[tuple[int, int], callable] = {
    (-1, 0): migrate_unversioned_to_v0,  # Special case: unversioned → v0
    (0, 1): migrate_v0_to_v1,  # Uncomment this line
    # Future migrations:
    # (1, 2): migrate_v1_to_v2,
}
```

#### Step 4: Create New Version Model

**Template is already provided!** See `dao/prog/config/versions/v1.py` for a commented template.

Uncomment and modify the template in `dao/prog/config/versions/v1.py`:

```python
"""Configuration schema version 1."""

from typing import Literal
from .v0 import ConfigurationV0


class ConfigurationV1(ConfigurationV0):
    """
    Configuration schema version 1.
    
    Changes from v0:
    - Add 'efficiency' as required field in BatteryConfig
    
    All other fields are inherited from ConfigurationV0.
    """
    
    config_version: Literal[1] = 1
    
    # Add your new or modified fields here
    # (they will override fields from V0)
```

#### Step 5: Update Loader

In `dao/prog/config/loader.py`, uncomment the import and update registries:

```python
from .versions.v0 import ConfigurationV0
from .versions.v1 import ConfigurationV1  # Uncomment this line

# Update this:
CURRENT_VERSION = 1  # Change from 0 to 1

# Add v1 to registry:
VERSION_MODELS: dict[int, Type[BaseModel]] = {
    0: ConfigurationV0,
    1: ConfigurationV1,  # Uncomment this line
}
```

#### Step 6: Update Wrapper and Schema Generator

Update imports to use the latest version:

**In `dao/prog/config/wrapper.py`:**
```python
from dao.prog.config.versions.v1 import ConfigurationV1  # Change from v0 to v1

# ... later in __init__:
self._config = ConfigurationV1(**migrated_data)  # Change from ConfigurationV0
```

**In `dao/prog/config/generate_docs.py`:**
```python
from dao.prog.config.versions.v1 import ConfigurationV1  # Change from v0 to v1

# ... later in generate_docs:
schema = ConfigurationV1.model_json_schema(...)  # Change from ConfigurationV0
```

#### Step 7: Write Tests

**Templates are already provided!** See `dao/tests/config/test_migrations.py` for commented examples.

Uncomment and modify the test templates in `dao/tests/config/test_migrations.py`:

```python
def test_v0_to_v1_adds_efficiency():
    """Test v0→v1 migration adds efficiency to batteries."""
    old_config = {
        "config_version": 0,
        "battery": [{"name": "Test", "capacity": 10, "max_charge_power": 5}]
    }
    
    from dao.prog.config.migrations.v0_to_v1 import migrate_v0_to_v1
    new_config = migrate_v0_to_v1(old_config)
    
    assert new_config['config_version'] == 1
    assert new_config['battery'][0]['efficiency'] == 0.95


def test_migrate_v0_to_v1_via_migrate_config():
    """Test full migration chain from v0 to v1 using migrate_config."""
    old_config = {
        "config_version": 0,
        "battery": [{"name": "Test", "capacity": 10}]
    }
    
    from dao.prog.config.migrations.migrator import migrate_config
    migrated = migrate_config(old_config, target_version=1)
    
    assert migrated['config_version'] == 1
    assert migrated['battery'][0]['efficiency'] == 0.95
```

#### Step 8: Test Migration

```bash
# Run migration tests
pytest dao/tests/config/test_migrations.py -v

# Test with real config
python -c "
from dao.prog.config.loader import ConfigurationLoader
from pathlib import Path
loader = ConfigurationLoader(Path('dao/data/options.json'))
config = loader.load_and_migrate()
print(f'Migrated to version {config[\"config_version\"]}')
"
```

### Migration Best Practices

1. **Always provide sensible defaults** in migrations
2. **Document why the migration is needed** in the migration function docstring
3. **Test both upgrade paths** (unversioned→v0→v1 AND v0→v1)
4. **Create backup** before first migration (automatic via ConfigurationLoader)
5. **Keep migrations idempotent** (safe to run multiple times)
6. **Don't modify old version models** - only add new versions

---

## Working with This Project

### Initial Setup

1. Clone and set up environment (see [DEVELOP.md](DEVELOP.md))
2. Copy `dao/data/options_example.json` → `dao/data/options.json`
3. Create `dao/data/secrets.json` with your credentials
4. Configure database settings for your environment

### Making Changes

1. **Understand the impact:**
   - Configuration changes affect user setups
   - Optimization changes affect energy scheduling
   - Database changes require migration

2. **Test thoroughly:**
   - Run unit tests
   - Test with example configurations
   - Verify schema generation: `python -m dao.prog.config.generate_docs`
   - Check web UI still works

3. **Update documentation:**
   - Update `DOCS.md` for user-facing changes
   - Update this file for developer-facing changes
   - Add docstrings/comments for complex logic

### Code Review Checklist

- [ ] Type hints on all functions
- [ ] Docstrings for public APIs
- [ ] Required vs Optional fields match code usage
- [ ] No mutable defaults
- [ ] Secrets use SecretStr
- [ ] Error handling for external calls
- [ ] Logging at appropriate levels
- [ ] Migration created if adding required field without default
- [ ] Tests pass (including migration tests)
- [ ] Documentation updated
- [ ] Schema generation works

---

## Resources

- **Main Documentation:** [DOCS.md](dao/DOCS.md)
- **Developer Guide:** [DEVELOP.md](DEVELOP.md)
- **GitHub Issues:** https://github.com/corneel27/day-ahead/issues
- **Discussions:** https://github.com/corneel27/day-ahead/discussions
- **MIP Documentation:** https://python-mip.com/
- **Pydantic Docs:** https://docs.pydantic.dev/2.10/

---

**Remember:** This project optimizes real-world energy systems. Incorrect calculations or configurations can lead to unexpected costs or behavior. Test thoroughly!
