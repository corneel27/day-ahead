# Day Ahead Optimizer - Pydantic Configuration Developer Guide

**Last Updated**: 2025-12-11  
**Configuration Version**: v0  
**Pydantic Version**: 2.10.3

This guide explains how to maintain and extend the Pydantic-based configuration system.

---

## Table of Contents
1. [Overview](#overview)
2. [Making a Key Required/Optional](#making-a-key-requiredoptional)
3. [Modifying Default Values](#modifying-default-values)
4. [Extending an Existing Model](#extending-an-existing-model)
5. [Creating a New Model](#creating-a-new-model)
6. [Using Direct Config Access](#using-direct-config-access)
7. [Migration Workflows](#migration-workflows)
8. [Testing Requirements](#testing-requirements)
9. [Common Pitfalls](#common-pitfalls)

---

## Overview

The configuration system consists of:
- **Pydantic Models**: Type-safe configuration models in `dao/prog/config/versions/`
- **Config Wrapper**: Backward-compatible wrapper in `dao/prog/config/wrapper.py`
- **Fallback Mode**: Automatic degradation to dict-based behavior on validation errors
- **Migrations**: Version migration logic in `dao/prog/config/migrations/`
- **Auto-Documentation**: GitHub Actions automatically regenerate docs when models change
- **Documentation Validation**: Build fails if any field lacks a description

**Two Access Patterns**:
1. **Wrapper (Recommended)**: `config.get(['key'])` - Backward compatible, supports fallback
2. **Direct (Performance)**: `config.battery[0].name` - Type-safe, faster, no fallback

**Documentation Auto-Generation**:
- ✅ `config_schema.json` auto-generated from Pydantic schema
- ✅ `SETTINGS.md` auto-generated from json schema
- ✅ GitHub Actions automatically regenerates when models change
- ✅ **All fields MUST have descriptions** - build fails otherwise
- ⚠️ Never edit generated docs manually - they regenerate from code!

**📚 See [DOCUMENTATION_VALIDATION.md](DOCUMENTATION_VALIDATION.md) for validation details**

---

## Making a Key Required/Optional

### Quick Reference: When Do You Need Migration?

| Change | Example | Migration Needed? | Reason |
|--------|---------|-------------------|--------|
| Add field with default | `field: str = Field(default="x")` | ❌ No | Pydantic treats it as optional |
| Add field with None | `field: str \| None = None` | ❌ No | Already optional |
| Add required field (no default) | `field: str` | ✅ Yes | Old configs will fail validation |
| Change optional → has default | `None` → `Field(default="x")` | ❌ No | Less strict, backward compatible |
| Change has default → required | `Field(default="x")` → `field: str` | ✅ Yes | Removing default breaks old configs |
| Change default value | `default="old"` → `default="new"` | ❌ No* | *Unless behavior changes significantly |

### Adding a Field with Default Value

**✅ NON-BREAKING** - No migration needed!

When you add a field with a default value, it's **automatically optional** in Pydantic. Old configurations without this field will use the default.

```python
# dao/prog/config/models/devices/battery.py
from pydantic import BaseModel, Field

class BatteryConfig(BaseModel):
    name: str
    capacity: float
    max_charge_power: float
    
    # NEW: Adding field with default - NO MIGRATION NEEDED!
    efficiency: float = Field(
        default=0.95, 
        ge=0.0, 
        le=1.0,
        description="Battery round-trip efficiency (0-1)"
    )
```

**Why no migration is needed**:
- Pydantic treats `Field(default=X)` as optional
- Old configs without `efficiency` automatically get `0.95`
- `is_required() == False` for fields with defaults
- Completely backward compatible!

### Making a Field Truly Required

**⚠️ BREAKING CHANGE** - Requires version migration!

Only needed if you want a field to be required WITHOUT a default value:

```python
# dao/prog/config/versions/v1.py
class BatteryV1(BaseModel):
    name: str
    capacity: float
    max_charge_power: float
    
    # Truly required - no default, will fail validation if missing
    efficiency: float = Field(
        ge=0.0, 
        le=1.0,
        description="Battery round-trip efficiency (0-1)"
    )
```

**This DOES need migration** because old configs missing `efficiency` will fail validation.

### Switching from Optional to Required

**⚠️ BREAKING CHANGE** - Requires version migration!

#### Step 1: Update the Model

```python
# dao/prog/config/versions/v0.py (or new version)
from pydantic import BaseModel, Field

class BatteryV0(BaseModel):
    name: str
    capacity: float
    max_charge_power: float
    
    # BEFORE: Optional field
    # efficiency: float | None = None
    
    # AFTER Option 1: "Required" with default - NO MIGRATION NEEDED
    efficiency: float = Field(default=0.95, ge=0.0, le=1.0)
    
    # AFTER Option 2: Truly required - NEEDS MIGRATION
    # efficiency: float = Field(ge=0.0, le=1.0)  # No default!
```

#### Step 2: Create Migration (only if truly required without default)

**Skip this step if your field has a default value!**

Only create a migration if you're making a field required WITHOUT a default:

```python
# dao/prog/config/migrations/v0_to_v1.py
def migrate_v0_to_v1(old_config: dict) -> dict:
    """Migrate from v0 to v1."""
    new_config = old_config.copy()
    
    # Add required field to all batteries
    if 'battery' in new_config:
        for battery in new_config['battery']:
            if 'efficiency' not in battery:
                battery['efficiency'] = 0.95  # Provide migration default
    
    new_config['version'] = 1
    return new_config

# Register in dao/prog/config/migrations/__init__.py
from .v0_to_v1 import migrate_v0_to_v1

MIGRATIONS = {
    (0, 1): migrate_v0_to_v1,
}
```

#### Step 3: Update Version Number

```python
# dao/prog/config/versions/v1.py
class ConfigurationV1(BaseModel):
    version: Literal[1] = 1
    # ... rest of model
```

#### Step 4: Update Loader

```python
# dao/prog/config/loader.py
from .versions.v1 import ConfigurationV1

CURRENT_VERSION = 1
VERSION_MODELS = {
    0: ConfigurationV0,
    1: ConfigurationV1,  # Add new version
}
```

#### Step 5: Test

```python
# dao/tests/config/test_migrations.py
def test_v0_to_v1_adds_efficiency():
    old_config = {
        "version": 0,
        "battery": [{"name": "Test", "capacity": 10, "max_charge_power": 5}]
    }
    
    new_config = migrate_v0_to_v1(old_config)
    
    assert new_config['version'] == 1
    assert new_config['battery'][0]['efficiency'] == 0.95
```

### Switching from Required to Optional

**✅ NON-BREAKING** - No migration needed!

```python
# dao/prog/config/versions/v0.py
class BatteryV0(BaseModel):
    name: str
    capacity: float
    
    # BEFORE: Required field (no default)
    # efficiency: float
    
    # AFTER Option 1: Optional with default
    efficiency: float = Field(default=0.95, description="Efficiency rating")
    
    # AFTER Option 2: Truly optional (can be None)
    efficiency: float | None = Field(default=None, description="Efficiency rating")
```

**Note**: Making a field optional never breaks existing configs - they'll just keep providing the value.

---

## Modifying Default Values

### Safe Default Changes (Non-Breaking)

Changes that don't affect existing behavior:

```python
# dao/prog/config/versions/v0.py
class GraphicsV0(BaseModel):
    # BEFORE
    # style: str = "default"
    
    # AFTER - More permissive default
    style: str = "dark_background"  # ✅ Safe - just changes new configs
```

### Breaking Default Changes

If the new default changes behavior significantly:

#### Option 1: Keep Old Default, Document New Recommendation

```python
class SchedulerV0(BaseModel):
    # Keep old default for backward compatibility
    interval: str = "5min"  # Recommended: 15min for most users
```

```python
# Update documentation
"""
interval: Optimization interval
    Default: "5min" (for backward compatibility)
    Recommended: "15min" for typical home installations
    Options: "5min", "15min", "30min", "1h"
"""
```

#### Option 2: Create New Version with Migration

```python
# dao/prog/config/migrations/v0_to_v1.py
def migrate_v0_to_v1(old_config: dict) -> dict:
    new_config = old_config.copy()
    
    # Only update if using old default
    if 'scheduler' in new_config:
        scheduler = new_config['scheduler']
        if scheduler.get('interval') == '5min':
            # Migrate to new recommended default
            scheduler['interval'] = '15min'
    
    new_config['version'] = 1
    return new_config
```

---

## Extending an Existing Model

### Adding a New Optional Field

**✅ NON-BREAKING** - Add directly to current version:

```python
# dao/prog/config/models/devices/battery.py
class BatteryConfig(BaseModel):
    name: str
    capacity: float
    max_charge_power: float
    efficiency: float | None = None
    
    # NEW: Add optional field
    temperature_sensor: str | None = Field(
        default=None,
        description="Home Assistant entity ID for battery temperature sensor"
    )
```

**Important**: After adding the field:
1. Commit and push your changes
2. GitHub Actions will automatically regenerate `SETTINGS.md` and `config_schema.json`
3. The new field will appear in the documentation automatically!

### Adding a New Required Field

**⚠️ BREAKING CHANGE** - Requires new version + migration (see [Making a Key Required](#switching-from-optional-to-required))

### Adding Validation

```python
from pydantic import BaseModel, Field, field_validator

class BatteryV0(BaseModel):
    capacity: float = Field(gt=0, description="Battery capacity in kWh")
    
    @field_validator('capacity')
    @classmethod
    def validate_capacity(cls, v: float) -> float:
        if v > 1000:
            raise ValueError('Battery capacity unreasonably large (>1000 kWh)')
        return v
```

### Adding Computed Fields

```python
from pydantic import computed_field

class BatteryV0(BaseModel):
    capacity: float  # kWh
    voltage: float   # V
    
    @computed_field
    @property
    def capacity_wh(self) -> float:
        """Capacity in Watt-hours."""
        return self.capacity * 1000
```

---

## Creating a New Model

### Step 1: Define the Model

**⚠️ IMPORTANT**: All fields MUST have descriptions or the build will fail!

```python
# dao/prog/config/models/heat_pump.py
from pydantic import BaseModel, Field

class HeatPumpV0(BaseModel):
    """Heat pump configuration."""
    
    model_config = {"extra": "allow"}  # Preserve unknown keys
    
    # ✅ REQUIRED: All fields must have description
    name: str = Field(description="Heat pump name")
    cop: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="Coefficient of Performance (COP) rating"
    )
    max_power: float = Field(
        gt=0,
        description="Maximum power output in kW"
    )
    entity_id: str = Field(
        description="Home Assistant entity ID for heat pump control"
    )
    
    # Optional features - still need descriptions!
    temperature_sensor: str | None = Field(
        default=None,
        description="Optional temperature sensor entity ID for monitoring"
    )
```

**Documentation Validation**:
- Every field needs `Field(description="...")`
- Descriptions should be clear and meaningful
- Build will fail if any field lacks description
- Run `python -m dao.prog.config.generate_docs` to validate locally

### Step 2: Add to Root Configuration

```python
# dao/prog/config/versions/v0.py
from ..models.heat_pump import HeatPumpV0

class ConfigurationV0(BaseModel):
    version: Literal[0] = 0
    
    # Existing fields...
    battery: list[BatteryV0] = Field(default_factory=list)
    
    # NEW: Add your model
    heat_pump: list[HeatPumpV0] | None = Field(
        default=None,
        description="Heat pump configurations"
    )
```

### Step 3: Update Wrapper (if needed)

If you need special access methods:

```python
# dao/prog/config/wrapper.py
class Config:
    def get_heat_pumps(self) -> list:
        """Get all configured heat pumps."""
        if self._using_fallback:
            return self.get(['heat_pump']) or []
        return self._config.heat_pump or []
```

### Step 4: Add Tests

```python
# dao/tests/config/test_heat_pump.py
import pytest
from dao.prog.config.models.heat_pump import HeatPumpV0

def test_heat_pump_basic():
    hp = HeatPumpV0(
        name="Main HP",
        cop=3.5,
        max_power=5.0,
        entity_id="climate.heat_pump"
    )
    assert hp.name == "Main HP"
    assert hp.cop == 3.5

def test_heat_pump_cop_validation():
    with pytest.raises(ValueError, match="greater than or equal to 1.0"):
        HeatPumpV0(
            name="Bad HP",
            cop=0.5,  # Invalid COP
            max_power=5.0,
            entity_id="climate.heat_pump"
        )
```

### Step 5: Documentation Auto-Updates

**No manual documentation needed!** 📚

When you commit your new model:
1. Push your changes to GitHub
2. GitHub Actions detects the model change
3. Automatically regenerates `SETTINGS.md` and `config_schema.json`
4. Commits the updated docs back to your branch
5. Your PR gets a comment confirming docs were updated

**Manual regeneration (for local testing)**:
```bash
# Generate documentation
python -m dao.prog.config.generate_docs

# Generate schema
python -m dao.prog.config.generate_schema
```

The documentation will automatically include:
- ✅ All fields with their types
- ✅ Required/optional status
- ✅ Default values
- ✅ Field descriptions from `Field(description=...)`
- ✅ Validation constraints
- ✅ Model docstrings

### Fields
- `name`: Heat pump identifier
- `cop`: Coefficient of Performance (1.0-10.0, default: 3.0)
- `max_power`: Maximum power consumption in kW
- `entity_id`: Home Assistant entity ID
- `temperature_sensor`: Optional temperature sensor entity ID
```

---

## Using Direct Config Access

### When to Use Direct Access

**Use Direct Access When**:
- ✅ Performance-critical code paths
- ✅ Type hints and IDE autocomplete are important
- ✅ You're writing new code
- ✅ Config is guaranteed to be valid (fallback mode won't trigger)

**Use Wrapper When**:
- ✅ Backward compatibility matters
- ✅ Config might be invalid (want fallback mode)
- ✅ Dynamic/computed paths: `config.get(['battery', str(i), 'name'])`
- ✅ Working with legacy code

### Examples

#### Direct Access (Type-Safe)

```python
from dao.prog.da_config import Config

config = Config()

# Direct attribute access - fastest, type-safe
interval = config.scheduler.interval  # str
style = config.graphics.style  # str
batteries = config.battery  # list[BatteryV0]

# Array access
first_battery = config.battery[0]
battery_name = config.battery[0].name  # str
battery_capacity = config.battery[0].capacity  # float

# Nested objects
db_engine = config.database_da.engine  # str
db_host = config.database_da.host  # str | None

# Type checking works!
def process_battery(battery: BatteryV0) -> None:
    # IDE knows all fields and types
    print(f"{battery.name}: {battery.capacity}kWh")

for battery in config.battery:
    process_battery(battery)  # ✅ Type-safe
```

#### Wrapper Access (Backward Compatible)

```python
from dao.prog.da_config import Config

config = Config()

# get() method - slower, but safe with fallback
interval = config.get(['scheduler', 'interval'])  # Any
style = config.get(['graphics', 'style'])  # Any
batteries = config.get(['battery'])  # Any

# Dynamic paths
battery_idx = 0
battery_name = config.get(['battery', str(battery_idx), 'name'])

# With defaults
unknown_value = config.get(['some', 'missing', 'key'], default='fallback')

# Still works if config is invalid (fallback mode)
```

#### Mixed Approach (Recommended)

```python
from dao.prog.da_config import Config

config = Config()

# Use direct access for known paths
if not config._using_fallback:
    # Fast path - use Pydantic models
    for battery in config.battery:
        optimize_battery(
            name=battery.name,
            capacity=battery.capacity,
            efficiency=battery.efficiency or 0.95
        )
else:
    # Fallback path - use wrapper
    for i, battery in enumerate(config.get(['battery']) or []):
        optimize_battery(
            name=battery.get('name'),
            capacity=battery.get('capacity'),
            efficiency=battery.get('efficiency', 0.95)
        )
```

### Performance Comparison

```python
import timeit

# Direct access: ~0.1 µs
timeit.timeit('config.scheduler.interval', setup='from dao.prog.da_config import Config; config = Config()', number=100000)
# ~0.01 ms

# Wrapper access: ~2 µs  
timeit.timeit("config.get(['scheduler', 'interval'])", setup='from dao.prog.da_config import Config; config = Config()', number=100000)
# ~0.20 ms

# Direct is ~20x faster, but both are fast enough for most uses
```

---

## Migration Workflows

### Creating a New Version

1. **Copy previous version**:
```bash
cp dao/prog/config/versions/v0.py dao/prog/config/versions/v1.py
```

2. **Update version number**:
```python
# dao/prog/config/versions/v1.py
from typing import Literal

class ConfigurationV1(BaseModel):
    version: Literal[1] = 1  # Change from 0 to 1
    # ... rest of model
```

3. **Make your changes** (add fields, change types, etc.)

4. **Create migration function**:
```python
# dao/prog/config/migrations/v0_to_v1.py
def migrate_v0_to_v1(old_config: dict) -> dict:
    """Migrate configuration from v0 to v1.
    
    Changes:
    - Added required 'efficiency' field to battery
    - Changed scheduler.interval default from "5min" to "15min"
    """
    new_config = old_config.copy()
    
    # Add efficiency to batteries
    if 'battery' in new_config:
        for battery in new_config['battery']:
            if 'efficiency' not in battery:
                battery['efficiency'] = 0.95
    
    # Update scheduler interval if using old default
    if 'scheduler' in new_config:
        if new_config['scheduler'].get('interval') == '5min':
            new_config['scheduler']['interval'] = '15min'
    
    new_config['version'] = 1
    return new_config
```

5. **Register migration**:
```python
# dao/prog/config/migrations/__init__.py
from .v0_to_v1 import migrate_v0_to_v1

MIGRATIONS = {
    (0, 1): migrate_v0_to_v1,
}
```

6. **Update loader**:
```python
# dao/prog/config/loader.py
from .versions.v1 import ConfigurationV1

CURRENT_VERSION = 1
VERSION_MODELS = {
    0: ConfigurationV0,
    1: ConfigurationV1,
}
```

7. **Test migration**:
```python
# dao/tests/config/test_migrations.py
def test_migrate_v0_to_v1():
    old_config = {
        "version": 0,
        "battery": [{"name": "Test", "capacity": 10}],
        "scheduler": {"interval": "5min"}
    }
    
    new_config = migrate_v0_to_v1(old_config)
    
    assert new_config['version'] == 1
    assert new_config['battery'][0]['efficiency'] == 0.95
    assert new_config['scheduler']['interval'] == '15min'
```

### Backward Compatibility Promise

- **Old configs MUST continue to work** (via migration or fallback)
- **Migration is automatic** (user doesn't need to do anything)
- **Fallback mode** catches any issues and keeps system running
- **Loud warnings** alert users to config problems

---

## Testing Requirements

### Model Tests

Every model should have tests:

```python
# dao/tests/config/test_battery.py
import pytest
from dao.prog.config.models.battery import BatteryV0

def test_battery_basic():
    """Test basic battery creation."""
    battery = BatteryV0(
        name="Test Battery",
        capacity=10.0,
        max_charge_power=5.0
    )
    assert battery.name == "Test Battery"
    assert battery.capacity == 10.0

def test_battery_validation():
    """Test battery validation rules."""
    with pytest.raises(ValueError):
        BatteryV0(
            name="Bad Battery",
            capacity=-5.0,  # Invalid: negative capacity
            max_charge_power=5.0
        )

def test_battery_optional_fields():
    """Test optional fields have correct defaults."""
    battery = BatteryV0(name="Test", capacity=10, max_charge_power=5)
    assert battery.efficiency is None

def test_battery_extra_fields_preserved():
    """Test unknown fields are preserved (extra='allow')."""
    battery = BatteryV0(
        name="Test",
        capacity=10,
        max_charge_power=5,
        custom_field="custom_value"
    )
    assert battery.model_extra['custom_field'] == "custom_value"
```

### Integration Tests

Test with real configuration:

```python
# dao/tests/config/test_integration.py
def test_load_example_config():
    """Test loading the example configuration."""
    from dao.prog.da_config import Config
    
    config = Config()
    assert not config._using_fallback
    assert config.version == 0
    assert len(config.battery) > 0

def test_wrapper_compatibility():
    """Test wrapper provides backward-compatible interface."""
    from dao.prog.da_config import Config
    
    config = Config()
    
    # get() method works
    interval = config.get(['scheduler', 'interval'])
    assert interval is not None
    
    # Direct access works
    assert config.scheduler.interval == interval
```

### Migration Tests

Test every migration:

```python
# dao/tests/config/test_migrations.py
def test_all_migrations():
    """Test migrating through all versions."""
    from dao.prog.config.loader import ConfigurationLoader
    
    # Start with v0 config
    old_config = {
        "version": 0,
        "battery": [{"name": "Test", "capacity": 10}]
    }
    
    loader = ConfigurationLoader()
    result = loader.load_dict(old_config)
    
    # Should migrate to current version
    assert result.version == CURRENT_VERSION
```

### Fallback Tests

Test fallback mode:

```python
# dao/tests/config/test_fallback.py
def test_fallback_mode_activates():
    """Test fallback mode activates on invalid config."""
    from dao.prog.config.wrapper import Config
    
    # Create config with invalid data
    invalid_config = {"battery": [{"invalid": "data"}]}
    
    config = Config(config_dict=invalid_config)
    assert config._using_fallback
    assert config._pydantic_error is not None

def test_fallback_mode_still_works():
    """Test system continues working in fallback mode."""
    from dao.prog.config.wrapper import Config
    
    config = Config(config_dict={"test": "value"})
    assert config._using_fallback
    
    # get() still works
    value = config.get(['test'])
    assert value == "value"
```

---

## Common Pitfalls

### 1. Forgetting `extra="allow"`

**Problem**: Unknown fields are rejected by Pydantic.

```python
# ❌ BAD - rejects unknown fields
class BatteryV0(BaseModel):
    name: str
    capacity: float

# ✅ GOOD - preserves unknown fields
class BatteryV0(BaseModel):
    model_config = {"extra": "allow"}
    
    name: str
    capacity: float
```

### 2. Making Fields Required Without Migration

**Problem**: Existing configs break.

```python
# ❌ BAD - breaks existing configs
class BatteryV0(BaseModel):
    name: str
    capacity: float
    efficiency: float  # Newly required!

# ✅ GOOD - optional or with default
class BatteryV0(BaseModel):
    name: str
    capacity: float
    efficiency: float = 0.95  # Has default

# ✅ BETTER - optional with migration in next version
class BatteryV0(BaseModel):
    name: str
    capacity: float
    efficiency: float | None = None  # Optional in v0
    
# Then in v1 with migration:
class BatteryV1(BaseModel):
    name: str
    capacity: float
    efficiency: float = 0.95  # Required with default
```

### 3. Changing Field Types Without Migration

**Problem**: Type mismatches cause validation errors.

```python
# ❌ BAD - changes type without migration
# v0: interval: str = "15min"
# v1: interval: int = 15  # BREAKING!

# ✅ GOOD - union type allows both
class SchedulerV1(BaseModel):
    interval: str | int = "15min"
    
    @field_validator('interval')
    @classmethod
    def normalize_interval(cls, v):
        if isinstance(v, int):
            return f"{v}min"
        return v
```

### 4. Not Testing Fallback Mode

**Problem**: Fallback mode fails silently in production.

```python
# ✅ ALWAYS test both modes
def test_normal_mode():
    config = Config()  # Valid config
    assert not config._using_fallback
    value = config.get(['key'])

def test_fallback_mode():
    config = Config(config_dict={"invalid": "data"})
    assert config._using_fallback
    value = config.get(['key'], default='fallback')
```

### 5. Using Mutable Defaults

**Problem**: Shared mutable default values.

```python
# ❌ BAD - all instances share same list!
class ConfigV0(BaseModel):
    battery: list[BatteryV0] = []

# ✅ GOOD - use default_factory
class ConfigV0(BaseModel):
    battery: list[BatteryV0] = Field(default_factory=list)
```

### 6. Forgetting to Update CURRENT_VERSION

**Problem**: New version not recognized.

```python
# dao/prog/config/loader.py

# ❌ BAD - forgot to update
CURRENT_VERSION = 0  # Should be 1!
VERSION_MODELS = {
    0: ConfigurationV0,
    1: ConfigurationV1,  # New version not used
}

# ✅ GOOD - update both
CURRENT_VERSION = 1
VERSION_MODELS = {
    0: ConfigurationV0,
    1: ConfigurationV1,
}
```

---

## Summary Checklist

### Adding Optional Field (with default or None)
- [ ] Add field to model with `Field(default=X)` or `field: Type | None = None`
- [ ] Add Field description for auto-documentation
- [ ] Add tests for new field
- [ ] Commit and push - **docs auto-generate!**
- [ ] **✅ No migration needed!**

### Adding Field with Default Value
- [ ] Add field with `Field(default=X, description="...")`
- [ ] Add tests for new field
- [ ] Commit and push - **docs auto-generate!**
- [ ] **✅ No migration needed!** (Pydantic treats it as optional)

### Adding Truly Required Field (no default)
- [ ] Create new version (vN+1)
- [ ] Add field WITHOUT default: `field: Type = Field(description="...")`
- [ ] Create migration to add field to old configs
- [ ] Update `CURRENT_VERSION` in loader
- [ ] Register migration in `migrations/__init__.py`
- [ ] Add migration tests
- [ ] Commit and push - **docs auto-generate!**
- [ ] **⚠️ Migration required!**

### Changing Defaults
- [ ] Assess if breaking or non-breaking
- [ ] If breaking: create new version + migration
- [ ] If non-breaking: update in current version
- [ ] Update Field description if needed
- [ ] Test both old and new configs
- [ ] Commit and push - **docs auto-generate!**

### Creating New Model
- [ ] Create model file in `dao/prog/config/models/`
- [ ] Add comprehensive docstring to the model class
- [ ] Add Field descriptions for all fields
- [ ] Set `model_config = {"extra": "allow"}` if needed
- [ ] Add to root `ConfigurationVN`
- [ ] Add wrapper methods if needed
- [ ] Write comprehensive tests
- [ ] Commit and push - **docs auto-generate!**

---

## Automated Documentation

### GitHub Actions Workflow

The repository includes a GitHub Actions workflow (`.github/workflows/generate-docs.yml`) that automatically:

1. **Detects changes** to Pydantic models:
   - `dao/prog/config/models/**/*.py`
   - `dao/prog/config/versions/**/*.py`
   - Generator scripts themselves

2. **Regenerates documentation**:
   - `SETTINGS.md` from model metadata
   - `config_schema.json` from Pydantic schema

3. **Commits changes** back to your branch automatically

4. **Comments on PRs** to notify you

### Workflow Benefits

- ✅ **Code is the source of truth**: Documentation always matches models
- ✅ **Zero maintenance**: No manual doc updates needed
- ✅ **Automatic validation**: Schema and docs stay in sync
- ✅ **Developer friendly**: Just write good Field descriptions

### Local Testing

Test documentation generation locally before pushing:

```bash
# Generate SETTINGS.md
python -m dao.prog.config.generate_docs

# Generate config_schema.json
python -m dao.prog.config.generate_schema

# Check the output
git diff SETTINGS.md config_schema.json
```

### Best Practices for Auto-Documentation

**Write good Field descriptions**:
```python
# ❌ BAD - no description
capacity: float

# ✅ GOOD - clear description
capacity: float = Field(
    description="Battery capacity in kWh"
)

# 🌟 EXCELLENT - description + constraints
capacity: float = Field(
    gt=0,
    description="Battery capacity in kWh (must be positive)"
)
```

**Write model docstrings**:
```python
# ✅ GOOD - helps users understand the model
class BatteryConfig(BaseModel):
    """Battery configuration for optimization.
    
    Defines battery capacity, charge/discharge curves,
    and SOC limits for the optimization algorithm.
    """
    name: str = Field(description="Battery identifier")
    # ...
```

**Use descriptive names**:
```python
# ❌ BAD
entity_al: str

# ✅ GOOD
entity_actual_level: str = Field(
    description="Home Assistant entity for current battery SOC percentage"
)
```

---

**Questions?** Check [FALLBACK_MODE.md](FALLBACK_MODE.md) for fallback behavior, [PLAN.md](PLAN.md) for overall architecture, or [.github/workflows/README.md](.github/workflows/README.md) for workflow details.

