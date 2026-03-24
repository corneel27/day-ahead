# Day Ahead Optimizer - Pydantic Configuration Developer Guide

**Last Updated**: 2026-03-12  
**Configuration Version**: v0  
**Pydantic Version**: 2.10.3

This guide explains how to maintain and extend the Pydantic-based configuration system.

---

## Table of Contents
1. [Overview](#overview)
2. [JSON Schema Extensions](#json-schema-extensions)
3. [Making a Key Required/Optional](#making-a-key-requiredoptional)
4. [Modifying Default Values](#modifying-default-values)
5. [Extending an Existing Model](#extending-an-existing-model)
6. [Validators](#validators)
7. [Working with EntityId](#working-with-entityid)
8. [Working with Secrets (SecretStr)](#working-with-secrets-secretstr)
9. [Working with Dynamic Values (FlexValue)](#working-with-dynamic-values-flexvalue)
10. [Creating a New Model](#creating-a-new-model)
10. [Migration Workflows](#migration-workflows)
11. [Testing Requirements](#testing-requirements)
12. [Common Pitfalls](#common-pitfalls)

---

## Overview

The configuration system consists of:
- **Pydantic Models**: Type-safe configuration models in `dao/prog/config/versions/`
- **Migrations**: Version migration logic in `dao/prog/config/migrations/`
- **Documentation**: `SETTINGS.md` and `config_schema.json` generated from code; run `python scripts/generate_docs.py` before committing, CI validates they are up to date

**Documentation:**
- ✅ `config_schema.json` auto-generated from Pydantic schema
- ✅ `SETTINGS.md` auto-generated from json schema
- ✅ **All fields MUST have descriptions** — CI build fails otherwise
- ⚠️ Never edit generated docs manually — they are regenerated from code!
- ⚠️ Run `python scripts/generate_docs.py` before committing model changes

---

## JSON Schema Extensions

The configuration system uses **JSON Schema extensions** (custom `x-*` fields) to provide rich metadata for documentation generation, UI hints, and better developer experience. All extensions follow the JSON Schema specification for custom properties.

### Why Use Extensions?

- **📄 Better Documentation**: Generate comprehensive SETTINGS.md with examples, tips, and detailed help
- **🎨 UI Hints**: Guide UI developers on widget types and entity filters
- **🔍 Validation Help**: Provide clear validation messages and hints
- **📊 Organization**: Categorize and order fields logically
- **🔗 External Links**: Link to detailed wiki documentation

### Available Extensions

#### Field-Level Extensions

These go in `json_schema_extra` dict within `Field()`:

| Extension | Type | Purpose | Example |
|-----------|------|---------|---------|
| `x-help` | `str` | Detailed help text with markdown, examples, and tips | See example below |
| `x-unit` | `str` | Physical unit of measurement | `"kWh"`, `"W"`, `"%"`, `"degrees"` |
| `x-ui-section` | `str` | UI form section/grouping hint | `"Battery Specifications"`, `"SOC Limits"`, `"Power Configuration"` |
| `x-validation-hint` | `str` | Explain validation constraints | `"Must be > 0, typically 40-100 kWh"` |
| `x-ui-widget` | `str` | Suggested UI widget type | `"entity-picker"`, `"slider"`, `"time-picker"` |
| `x-ui-widget-filter` | `str` | Filter for HA entity picker | `"sensor"`, `"switch"`, `"binary_sensor"` |
| `x-docs-url` | `str` | External documentation URL | `"https://github.com/.../wiki/Battery"` |

**Note:** `x-ui-section` is a **hint** for UI builders on how to group related fields. Documentation generators may ignore it.

#### Model-Level Extensions

These go in `ConfigDict` `json_schema_extra`:

| Extension | Type | Purpose | Example |
|-----------|------|---------|---------|
| `x-ui-group` | `str` | TOC section grouping | `"Energy"`, `"Devices"`, `"Integration"` |
| `x-icon` | `str` | Icon identifier (mapped to emoji) | `"battery-charging"`, `"solar-panel"`, `"ev-plug"` |
| `x-order` | `int` | Sort order within group | `1`, `2`, `3`, ... |
| `x-help` | `str` | Detailed model help (markdown) | Multi-line markdown with examples |
| `x-docs-url` | `str` | External documentation URL | `"https://github.com/.../wiki/Battery-Configuration"` |

### Complete Example: Field with Extensions

```python
from pydantic import BaseModel, Field

class BatteryConfig(BaseModel):
    capacity: float = Field(
        gt=0,
        description="Battery capacity in kWh",  # ✅ REQUIRED - shown in tables
        json_schema_extra={
            # Detailed help with examples and tips
            "x-help": """Total usable battery capacity in kilowatt-hours.

**Finding Your Capacity:**
- Check battery specifications (often less than advertised)
- Look for "usable capacity" or "effective capacity"
- Example: Tesla Powerwall 2 = 13.5 kWh usable

**Tips:**
- Use usable capacity, not total capacity
- Account for manufacturer SOC limits
- Multiple batteries: sum their capacities

**Common Values:**
- Home batteries: 5-15 kWh
- Large systems: 20-50 kWh
- Tesla Powerwall 2: 13.5 kWh
- LG RESU 10H: 9.8 kWh""",
            
            # Physical unit
            "x-unit": "kWh",
            
            # UI section grouping hint
            "x-ui-section": "Battery Specifications",
            
            # Validation explanation
            "x-validation-hint": "Must be > 0, typically 5-50 kWh for home systems",
            
            # UI widget suggestion
            "x-ui-widget": "number-input",
            
            # External documentation
            "x-docs-url": "https://github.com/corneel27/day-ahead/wiki/Battery-Capacity"
        }
    )
```

### Complete Example: Model with Extensions

```python
from pydantic import BaseModel, Field, ConfigDict

class BatteryConfig(BaseModel):
    """Battery configuration for optimization."""
    
    name: str = Field(description="Battery identifier")
    capacity: float = Field(gt=0, description="Battery capacity in kWh")
    # ... more fields ...
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            # TOC section grouping
            'x-ui-group': 'Energy',
            
            # Icon identifier (mapped to 🔋 emoji)
            'x-icon': 'battery-charging',
            
            # Sort order (1 = first in group)
            'x-order': 1,
            
            # Detailed model-level help
            'x-help': '''# Battery Configuration

Configure your home battery storage system for optimal energy management.

## Key Settings
- **Capacity**: Total storage capacity in kWh
- **SOC Limits**: Upper and lower charge limits
- **Power Stages**: Charging/discharging efficiency curves
- **Control Entities**: Home Assistant entities

## Optimization Strategy
The optimizer decides when to charge/discharge based on:
- Electricity prices (charge when cheap, discharge when expensive)
- Solar production forecasts
- Battery efficiency and degradation costs
- SOC limits and constraints

## Tips
- Set upper_limit to 80-90% for longer battery life
- Configure charge/discharge stages for accurate optimization
- Monitor battery degradation with cycle_cost setting
- Use optimal_lower_level for cost optimization''',
            
            # External documentation
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Battery-Configuration'
        }
    )
```

### UI Sections

Use `x-ui-section` to hint at logical grouping of related fields within a form:

**Purpose:** Helps UI builders organize fields into logical sections/groups. Documentation generators may ignore this.

**Common Sections:**
- **"Battery Specifications"**: Core capacity and identification
- **"SOC Limits"**: State of charge boundaries
- **"Power Configuration"**: Power levels and stages
- **"Efficiency Parameters"**: Conversion efficiencies
- **"Cost & Degradation"**: Economic parameters
- **"Control Entities"**: Home Assistant entity controls
- **"Panel Orientation"**: Solar panel positioning
- **"Temperature Parameters"**: Heating/cooling settings
- **"Connection Settings"**: Database/API connections
- **"Authentication"**: Credentials and tokens

**Note:** This is a **hint**, not a requirement. UI builders can group fields differently based on their UX needs.

### UI Groups

Use `x-ui-group` to organize models into logical documentation sections:

| Group | Purpose | Examples |
|-------|---------|----------|
| `"Energy"` | Energy systems | BatteryConfig, SolarConfig, GridConfig |
| `"Devices"` | Controllable devices | EVConfig, MachinesConfig |
| `"Heating"` | Heating systems | HeatingConfig, BoilerConfig |
| `"Integration"` | External integrations | DatabaseConfig, TibberConfig, DashboardConfig, NotificationsConfig |
| `"Pricing"` | Price data sources | PricingConfig |
| `"DAO"` | Core DAO settings | SchedulerConfig and configuration root fields |
| `"Reporting"` | Reporting & history | ReportConfig, HistoryConfig |
| `"Visualization"` | Graphics | GraphicsConfig |
| `"HASS"` | Home Assistant | HomeAssistantConfig |

### Icon Identifiers

Use `x-icon` with these identifiers (mapped to emojis in documentation):

| Identifier | Emoji | Used For |
|------------|-------|----------|
| `"battery-charging"` | 🔋 | Battery systems |
| `"solar-panel"` | ☀️ | Solar panels |
| `"ev-plug"` | 🚗 | Electric vehicles |
| `"thermometer"` | 🌡️ | Heating systems |
| `"water-boiler"` | 💧 | Boiler/DHW |
| `"washing-machine"` | 🧺 | Appliances/machines |
| `"database"` | 💾 | Databases |
| `"chart-line"` | 📈 | Graphics/charts |
| `"report"` | 📉 | Reports |
| `"bell"` | 🔔 | Notifications |
| `"clock"` | 🕐 | Scheduler/time |
| `"home"` | 🏠 | Home Assistant |
| `"lightning"` | ⚡ | Grid/power/Tibber |
| `"history"` | ⏰ | History tracking |
| `"dashboard"` | 📊 | Dashboard UI |
| `"currency"` | 💰 | Pricing |

### Writing Good Help Text

The `x-help` field supports full Markdown and should include:

1. **Clear Explanation**: What the field does
2. **Examples**: Concrete values or configurations
3. **Tips**: Best practices and gotchas
4. **Common Values**: Typical ranges
5. **Troubleshooting**: Common issues

**Example Template:**
```python
"x-help": """Brief one-line summary.

**What It Does:**
Clear explanation of the field's purpose and behavior.

**Examples:**
- Example 1: Description
- Example 2: Description

**Common Values:**
- Typical case 1: 10-20
- Typical case 2: 50-100

**Tips:**
- Tip 1 for best results
- Tip 2 to avoid issues

**Related:**
See also: field1, field2"""
```

### Validation Hints

Use `x-validation-hint` to explain constraints in human terms:

```python
# Instead of just: ge=0, le=100
"x-validation-hint": "0-100%, protects battery from deep discharge"

# Instead of just: gt=0
"x-validation-hint": "Must be > 0, typically 5-15 kWh for home systems"

# For enums:
"x-validation-hint": "Options: 'mysql', 'postgresql', 'sqlite'"

# For patterns:
"x-validation-hint": "Format: HHMM (e.g., '0430', 'xx00' for every hour)"
```

### Best Practices

1. **Always add extensions to new fields**:
   - Minimum: `x-ui-section`, `x-unit` (if applicable)
   - Recommended: Add `x-help` for complex fields
   - Optional: `x-ui-widget`, `x-ui-widget-filter` for UI hints

2. **Be consistent**:
   - Use same section names across similar fields
   - Use standard unit abbreviations (kWh, W, %, °C, etc.)
   - Follow existing patterns for help text structure

3. **Keep help text focused**:
   - Don't duplicate what's in the description
   - Add value with examples and tips
   - Link to external docs for deep dives

4. **Test generated documentation**:
   ```bash
   python scripts/generate_docs.py
   # Check SETTINGS.md for formatting
   ```

5. **Update ICON_MAP** if adding new icons:
   - Edit `scripts/generate_docs.py`
   - Add mapping: `"your-icon-id": "🔥"`

### Migration Considerations

Extensions are **metadata only** and do **not** affect:
- Configuration validation
- Runtime behavior  
- Backward compatibility

You can add/modify extensions without creating migrations!

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
    
    new_config['config_version'] = 1
    return new_config

# Register in dao/prog/config/migrations/migrator.py
from .v0_to_v1 import migrate_v0_to_v1

MIGRATIONS: dict[tuple[int, int], callable] = {
    (0, 1): migrate_v0_to_v1,
}
```

#### Step 3: Update Version Number

```python
# dao/prog/config/versions/v1.py
class ConfigurationV1(BaseModel):
    config_version: Literal[1] = 1
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
        "config_version": 0,
        "battery": [{"name": "Test", "capacity": 10, "max_charge_power": 5}]
    }
    
    new_config = migrate_v0_to_v1(old_config)
    
    assert new_config['config_version'] == 1
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
    
    new_config['config_version'] = 1
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

See the [Validators](#validators) section for `field_validator` (single field) and `model_validator` (cross-field) patterns.

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

## Validators

### Built-in Field constraints

**Prefer built-in constraints over custom validators whenever possible.** Built-in constraints are translated directly into `config_schema.json` (e.g. `"minimum"`, `"maxLength"`), which means the UI and documentation automatically reflect them. Custom validators run only in Python and are invisible to the schema.

Before writing a custom validator, check whether a built-in `Field` constraint is enough:

| Constraint | Types | Meaning |
|---|---|---|
| `gt=x` / `ge=x` | numeric | greater than / greater than or equal to |
| `lt=x` / `le=x` | numeric | less than / less than or equal to |
| `multiple_of=x` | numeric | value must be a multiple of `x` |
| `min_length=n` / `max_length=n` | `str`, `list` | length bounds |
| `pattern="regex"` | `str` | value must match regex |

```python
capacity: float = Field(gt=0, le=1000, description="Capacity in kWh")
name: str = Field(min_length=1, max_length=50, description="Battery name")
```

Full reference: [Pydantic field constraints docs](https://docs.pydantic.dev/latest/concepts/fields/#field-constraints)

---

### `field_validator` — Single-field validation

Use `@field_validator` when a constraint applies to a **single field** and cannot be expressed with `Field(gt=, le=, ...)` alone.

- Must be a `@classmethod`
- Receives the (already type-coerced) field value; return the (possibly transformed) value or raise `ValueError`
- `mode='before'` runs before type coercion; `mode='after'` (default) runs after

```python
from pydantic import BaseModel, Field, field_validator

class BatteryConfig(BaseModel):
    capacity: float = Field(gt=0, description="Capacity in kWh")

    @field_validator('capacity')
    @classmethod
    def validate_capacity(cls, v: float) -> float:
        if v > 1000:
            raise ValueError("Capacity > 1000 kWh is unreasonably large")
        return v  # return the (possibly transformed) value
```

### `model_validator` — Cross-field validation

Use `@model_validator` when a constraint involves **two or more fields**, or when you need to mutate the constructed model (e.g. prepend a sentinel entry to a list).

- `mode='after'` receives `self` (the fully constructed model); can read and write fields; always `return self`
- `mode='before'` receives the raw input `dict`; useful for pre-processing before field parsing

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal

class HeatingEnabled(BaseModel):
    adjustment: Literal['on/off', 'power', 'heating curve'] = 'power'
    stages: list = Field(default=[])

    @model_validator(mode='after')
    def validate_stages(self) -> 'HeatingEnabled':
        if len(self.stages) == 0 and self.adjustment in ('power', 'heating curve'):
            raise ValueError(f"At least one stage required when adjustment is '{self.adjustment}'")
        return self
```

### When to use which

| Situation | Use |
|-----------|-----|
| Validate or transform one field | `field_validator` |
| Constraint across two or more fields | `model_validator(mode='after')` |
| Pre-process raw input before field parsing | `model_validator(mode='before')` |
| Mutate a field (e.g. prepend a sentinel to a list) | `model_validator(mode='after')` |

> **Note on imports**: only import what you use — if only `model_validator` is needed, don't import `field_validator`.

---

## Working with EntityId

Use `EntityId` (defined in `dao/prog/config/models/base.py`) for **any field that holds a Home Assistant entity ID** — sensors, switches, input numbers, etc. Never type such fields as plain `str`.

`EntityId` subclasses `str` so it works everywhere a plain string is expected (f-strings, HA API calls) without any callsite changes.

### Why Not `str`?

A plain `str` field accepts any string, including typos like `"sensor_battery_soc"` (missing the dot). `EntityId` validates the `domain.object_id` format at parse time — bad configs fail loudly rather than silently producing wrong results at runtime.

Additionally, because `EntityId` is registered as a named `$ref` in the JSON schema, UI builders can automatically render an entity picker widget without needing any `x-ui-widget` hint.

### Field Declaration

```python
from .base import EntityId

class BatteryConfig(BaseModel):
    entity_actual_level: Optional[EntityId] = Field(
        default=None,
        alias="entity actual level",
        description="HA sensor for current battery SOC (%)",
        json_schema_extra={
            "x-ui-widget-filter": "sensor",
        },
    )
    entity_switch: Optional[EntityId] = Field(
        default=None,
        alias="entity switch",
        description="HA switch to control battery charge/discharge",
        json_schema_extra={
            "x-ui-widget-filter": "switch",
        },
    )
```

### Validation

`EntityId` accepts strings matching `domain.object_id` where the domain starts with a letter. Invalid values raise `ValueError` at parse time:

```python
EntityId("sensor.battery_soc")   # ✅ valid
EntityId("input_number.target")  # ✅ valid
EntityId("battery_soc")          # ❌ raises ValueError — missing domain
EntityId("0.45")                 # ❌ raises ValueError — domain starts with digit
```

---

## Working with Secrets (SecretStr)

Use `SecretStr` (defined in `dao/prog/config/models/base.py`) for **any field that holds a credential** — API tokens, database passwords, or long-lived access tokens. Never type such fields as plain `str`.

### Why Not `str`?

A plain `str` field accepts `"!secret key_name"` as a literal string — it is never looked up in `secrets.json`. `SecretStr` parses the `!secret` prefix and performs the lookup at runtime.

### Field Declaration

```python
from .base import SecretStr

class MyServiceV0(BaseModel):
    model_config = {"extra": "allow"}

    api_key: SecretStr = Field(
        description="API key for My Service (use !secret for security)",
        json_schema_extra={
            "x-help": "Store in secrets.json. Use: !secret my_service_api_key",
            "x-ui-section": "Integration",
        },
    )
    password: Optional[SecretStr] = Field(
        default=None,
        description="Password (optional, use !secret)",
    )
```

Do **not** use `SecretStr | str` or `str | SecretStr` union types. `SecretStr` already handles both cases:

| Config value | Stored as `secret_key` | `resolve()` returns |
|---|---|---|
| `"!secret my_key"` | `"my_key"` | Value looked up from `secrets.json` |
| `"plain_text_value"` | `"plain_text_value"` | The literal string itself (fallback) |

### Resolving at the Call Site

Call `.resolve(loader.secrets)` (or the appropriate `secrets` dict) wherever you need the actual value. Never store the resolved value long-term — always resolve on demand.

```python
# ✅ GOOD
api_key: str = config.my_service.api_key.resolve(loader.secrets)

# ❌ BAD - don't guard with isinstance; SecretStr always has resolve()
if isinstance(config.my_service.api_key, SecretStr):
    api_key = config.my_service.api_key.resolve(loader.secrets)
```

For `Optional[SecretStr]` fields, check for `None` first:

```python
api_key: str | None = (
    config.my_service.api_key.resolve(loader.secrets)
    if config.my_service.api_key is not None
    else None
)
```

### Serialization

`SecretStr` is a plain `str` subclass with no custom serializer. `model_dump()` returns the raw stored string — `"!secret key_name"` for references, or the literal value for plain-text passwords — exactly as it appears in `options.json`. This means round-tripping through `model_dump()` / `model_validate()` preserves the original config representation. The resolved (plain-text) value is never stored inside `SecretStr`, so serialization can never leak it.

---

## Working with Dynamic Values (FlexValue)

Use a `FlexValue` typed subclass for **any field that can be either a static/literal value or a live Home Assistant entity ID**. This allows users to hardcode a number in their config *or* point to a HA sensor that supplies the value at runtime.

### Typed subclasses

Always use a typed subclass rather than `FlexValue` directly. The subclass determines the type returned by `resolve()` without requiring a type argument at the call site:

| Class | Resolves to | Notes |
|---|---|---|
| `FlexFloat` | `float` | Numeric fields — SOC, power, temperature |
| `FlexInt` | `int` | Integer fields — percentages, counts. Float literals are truncated |
| `FlexBool` | `bool` | Boolean fields. HA states `"on"`, `"true"`, `"1"` all resolve to `True` |
| `FlexStr` | `str` | String fields — mode selectors, text sensors |
| `FlexEnum` | `str` | Like `FlexStr`, but validates literal values against an allowed set |

### How it works

`FlexValue` detects whether `value` looks like an entity ID (`domain.anything` pattern, domain starting with a letter). If so, `.resolve()` calls the provided HA state getter. Otherwise the stored literal is returned.

| Config value | Treated as | `resolve()` returns |
|---|---|---|
| `20` | Literal integer | `20` (cast to target type) |
| `0.5` | Literal float | `0.5` |
| `"sensor.battery_soc"` | HA entity ID | Live HA state, cast to target type |
| `"input_number.cooling_rate"` | HA entity ID | Live HA state, cast to target type |

**Note:** Numeric strings like `"0.45"` are *not* treated as entity IDs — the domain must start with a letter.

### Field Declaration

Do **not** use `float | FlexFloat` or bare `FlexValue`. Use just the typed subclass — bare literals are wrapped automatically via `parse_from_literal`.

```python
from .base import FlexFloat, FlexInt, FlexBool, FlexStr, FlexEnum

class MyDeviceV0(BaseModel):
    model_config = {"extra": "allow"}

    max_power: FlexFloat = Field(
        description="Max power in watts (can be HA entity)",
        json_schema_extra={
            "x-help": "Integer watts, or HA entity ID (e.g. sensor.inverter_max_power).",
            "x-unit": "W",
            "x-ui-widget-filter": "sensor,input_number",
        },
    )
    penalty: Optional[FlexFloat] = Field(
        default=None,
        description="Penalty cost per unit (can be HA entity)",
    )
```

For fields with a sensible default, wrap the default in the typed subclass:

```python
    degree_days_factor: FlexFloat = Field(
        default=FlexFloat(value=1.0),
        alias="degree days factor",
        description="Degree days factor (can be HA entity)",
    )
```

### Resolving at the Call Site

Pass a callable `(entity_id: str) -> str` as the only argument. In `DaBase`/`DaCalc` this is always `lambda eid: self.get_state(eid).state`. Define it once per method and reuse.

Note: Unlike the old API, **no type argument** is passed — the type is encoded in the subclass:

```python
ha_getter = lambda eid: self.get_state(eid).state

# Required field — type inferred from FlexFloat subclass
max_power: float = config.my_device.max_power.resolve(ha_getter)

# Optional field — guard for None first
penalty_field = config.my_device.penalty
penalty: float = penalty_field.resolve(ha_getter) if penalty_field is not None else 0.0
```

### FlexEnum — validated string choices

Use `FlexEnum` when a field has a fixed set of allowed values *or* a HA entity ID.
Declare the allowed values once in the field default. The default value is required to provide the allowed set for validation and documentation.

```python
from .base import FlexEnum

class SchedulerConfig(DAOConfigBaseModel):
    strategy: FlexEnum = Field(
        default=FlexEnum(
            value="minimize cost",
            enum_values=["minimize cost", "minimize consumption"],
        ),
        description="Optimization strategy",
    )
```

All DAO config models inherit from `DAOConfigBaseModel`, so no further setup is needed.

### Testing

In tests where you know the value is literal, pass a no-op getter that asserts it is never called:

```python
def no_ha_calls(entity_id: str) -> str:
    raise AssertionError(f"Unexpected HA lookup: {entity_id}")

result = flex_val.resolve(no_ha_calls)  # safe when value is a literal
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
- Run `python scripts/generate_docs.py` to validate locally

### Step 2: Add to Root Configuration

```python
# dao/prog/config/versions/v0.py
from ..models.heat_pump import HeatPumpV0

class ConfigurationV0(BaseModel):
    config_version: Literal[0] = 0
    
    # Existing fields...
    battery: list[BatteryV0] = Field(default_factory=list)
    
    # NEW: Add your model
    heat_pump: list[HeatPumpV0] | None = Field(
        default=None,
        description="Heat pump configurations"
    )
```

### Step 3: Add Tests

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

### Step 4: Documentation Auto-Updates

**No manual documentation needed!** 📚

When you commit your new model:
1. Push your changes to GitHub
2. GitHub Actions detects the model change
3. Automatically regenerates `SETTINGS.md` and `config_schema.json`
4. Commits the updated docs back to your branch
5. Your PR gets a comment confirming docs were updated

**Manual regeneration (for local testing)**:
```bash
# Generate documentation and schema
python scripts/generate_docs.py
```

The documentation will automatically include:
- ✅ All fields with their types
- ✅ Required/optional status
- ✅ Default values
- ✅ Field descriptions from `Field(description=...)`
- ✅ Validation constraints
- ✅ Model docstrings


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
    config_version: Literal[1] = 1  # Change from 0 to 1
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
    
    new_config['config_version'] = 1
    return new_config
```

5. **Register migration**:
```python
# dao/prog/config/migrations/migrator.py
from .v0_to_v1 import migrate_v0_to_v1

MIGRATIONS: dict[tuple[int, int], callable] = {
    (-1, 0): migrate_unversioned_to_v0,
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
        "config_version": 0,
        "battery": [{"name": "Test", "capacity": 10}],
        "scheduler": {"interval": "5min"}
    }
    
    new_config = migrate_v0_to_v1(old_config)
    
    assert new_config['config_version'] == 1
    assert new_config['battery'][0]['efficiency'] == 0.95
    assert new_config['scheduler']['interval'] == '15min'
```

### Backward Compatibility Promise

- **Old configs MUST continue to work** (via migration)
- **Migration is automatic** (user doesn't need to do anything)
- **Loud warnings** alert users to config problems

---

## Testing Requirements

### Model Tests

Every model should have tests:

```python
# dao/tests/config/test_battery.py
import pytest
from dao.prog.config.models.devices.battery import BatteryConfig

def test_battery_basic():
    """Test basic battery creation."""
    battery = BatteryConfig(
        name="Test Battery",
        capacity=10.0,
        max_charge_power=5.0
    )
    assert battery.name == "Test Battery"
    assert battery.capacity == 10.0

def test_battery_validation():
    """Test battery validation rules."""
    with pytest.raises(ValueError):
        BatteryConfig(
            name="Bad Battery",
            capacity=-5.0,  # Invalid: negative capacity
            max_charge_power=5.0
        )

def test_battery_optional_fields():
    """Test optional fields have correct defaults."""
    battery = BatteryConfig(name="Test", capacity=10, max_charge_power=5)
    assert battery.efficiency is None

def test_battery_extra_fields_preserved():
    """Test unknown fields are preserved (extra='allow')."""
    battery = BatteryConfig(
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
    from pathlib import Path
    from dao.prog.config.loader import ConfigurationLoader
    
    loader = ConfigurationLoader(Path("dao/data/options.json"))
    config = loader.load_and_validate()
    assert config.config_version == 0
    assert len(config.battery) > 0
```

### Migration Tests

Test every migration:

```python
# dao/tests/config/test_migrations.py
def test_all_migrations():
    """Test migrating through all versions."""
    from dao.prog.config.migrations.migrator import migrate_config
    from dao.prog.config.loader import CURRENT_VERSION
    
    # Start with unversioned config
    old_config = {
        "battery": [{"name": "Test", "capacity": 10}]
    }
    
    result = migrate_config(old_config, target_version=CURRENT_VERSION)
    
    # Should migrate to current version
    assert result['config_version'] == CURRENT_VERSION
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

### 4. Using Mutable Defaults

**Problem**: Shared mutable default values.

```python
# ❌ BAD - all instances share same list!
class ConfigV0(BaseModel):
    battery: list[BatteryV0] = []

# ✅ GOOD - use default_factory
class ConfigV0(BaseModel):
    battery: list[BatteryV0] = Field(default_factory=list)
```

### 5. Forgetting to Update CURRENT_VERSION

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

### Adding Optional or Defaulted Field
- [ ] Add field with `Field(default=X, description="...")` or `field: Type | None = None`
- [ ] Add tests for new field
- [ ] Regenerate docs: `python scripts/generate_docs.py`
- [ ] **✅ No migration needed!**

### Adding Truly Required Field (no default)
- [ ] Create new version (vN+1)
- [ ] Add field WITHOUT default: `field: Type = Field(description="...")`
- [ ] Create migration to add field to old configs
- [ ] Update `CURRENT_VERSION` in loader
- [ ] Register migration in `migrations/migrator.py`
- [ ] Add migration tests
- [ ] Regenerate docs: `python scripts/generate_docs.py`
- [ ] **⚠️ Migration required!**

### Changing Defaults
- [ ] Assess if breaking or non-breaking
- [ ] If breaking: create new version + migration
- [ ] If non-breaking: update in current version
- [ ] Update Field description if needed
- [ ] Test both old and new configs
- [ ] Regenerate docs: `python scripts/generate_docs.py`

### Creating New Model
- [ ] Create model file in `dao/prog/config/models/`
- [ ] Add comprehensive docstring to the model class
- [ ] Add Field descriptions for all fields
- [ ] Set `model_config = {"extra": "allow"}` if needed
- [ ] Add to root `ConfigurationVN`
- [ ] Write comprehensive tests
- [ ] Regenerate docs: `python scripts/generate_docs.py`

---

## Automated Documentation

Developers generate `SETTINGS.md` and `config_schema.json` locally by running:

```bash
python scripts/generate_docs.py
git diff SETTINGS.md config_schema.json
```

CI validates that the generated files are up to date — the build fails if models were changed without regenerating the docs. Never edit those files manually.

---

**Questions?** See [PLAN.md](PLAN.md) for overall architecture, or [.github/workflows/README.md](.github/workflows/README.md) for workflow details.

