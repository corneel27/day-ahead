"""
Base models and utilities for Pydantic configuration.

This module provides:
- FlexValue: Base class for values that can be literals OR Home Assistant entity IDs
- FlexFloat / FlexInt / FlexBool: Typed variants — same flex behaviour, typed resolve()
- SecretStr: Secure handling of secrets loaded from secrets.json
- Base configuration utilities
"""

import re
from typing import Any, ClassVar, Optional, Union
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_serializer, model_validator, ConfigDict
from pydantic_core import core_schema as _core_schema

# Matches Home Assistant entity IDs: "domain.object_id"
# domain must start with a letter (rules out numeric strings like "0.45")
_HA_ENTITY_ID_RE = re.compile(r'^[a-z_][a-z0-9_]*\.[a-z0-9_]+$')

# Re-use a single TypeAdapter for bool coercion — Pydantic's lax bool validator
# accepts "true"/"false", "1"/"0", "on"/"off", "yes"/"no", integers, etc.
_bool_adapter = TypeAdapter(bool)


def _validate_entity_id(v: str) -> str:
    """Raise ValueError if *v* is not a valid Home Assistant entity ID."""
    if not _HA_ENTITY_ID_RE.match(v):
        raise ValueError(
            f"Invalid Home Assistant entity ID: {v!r}. "
            "Expected format: 'domain.object_id' (e.g. 'sensor.battery_soc')."
        )
    return v


class EntityId(str):
    """Home Assistant entity ID.

    Subclasses ``str`` so it is usable everywhere a plain string is expected
    (f-strings, ``split()``, hassapi, SQLAlchemy) with no callsite changes.
    Adding ``ref='EntityId'`` to the core schema causes Pydantic to emit a
    named ``$defs/EntityId`` entry and ``$ref`` pointers in the JSON schema,
    enabling type-based UI rendering without any ``x-ui-widget`` hints.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return _core_schema.no_info_after_validator_function(
            cls._validate,
            _core_schema.str_schema(),
            ref='EntityId',
        )

    @classmethod
    def _validate(cls, v: str) -> 'EntityId':
        if not _HA_ENTITY_ID_RE.match(v):
            raise ValueError(
                f"Invalid Home Assistant entity ID: {v!r}. "
                "Expected format: 'domain.object_id' (e.g. 'sensor.battery_soc')."
            )
        return cls(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'type': 'string',
            'x-help': 'Home Assistant entity ID in the format "domain.object_id" '
                      '(e.g. "sensor.battery_soc").',
        }


class FlexValue(BaseModel):
    """
    Base class for flexible values that can be either a literal or a Home Assistant
    entity ID.

    Accepts bare literals in config (e.g. ``95``, ``0.5``, ``"sensor.battery_soc"``)
    and wraps them automatically.  At runtime call ``resolve()`` to get the final
    value — either the stored literal or a live HA state lookup.

    Use the typed subclasses for field declarations so the expected resolve type is
    explicit without having to pass it at the call site:

        FlexFloat  — resolves to ``float``
        FlexInt    — resolves to ``int``
        FlexBool   — resolves to ``bool``
        FlexStr    — resolves to ``str``

    Examples:
        FlexFloat(value=0.5)                   # Literal float
        FlexInt(value=95)                      # Literal integer
        FlexBool(value=True)                   # Literal boolean
        FlexStr(value="minimize cost")         # Literal string
        FlexFloat(value="sensor.battery_soc")  # HA entity ID — resolved at runtime
        FlexBool(value="binary_sensor.grid")   # HA entity ID — resolved at runtime
    """

    # Subclasses declare their target resolve type here.
    # Any on the base = no coercion; typed subclasses override this.
    _resolve_type: ClassVar[Any] = Any

    value: Union[int, float, str, bool] = Field()

    model_config = ConfigDict(
        extra='forbid'
    )

    @model_serializer
    def serialize_flex_value(self) -> Any:
        """Serialize to the bare value for flat JSON representation."""
        return self.value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        """Return the JSON schema for the union type."""
        return {
            'anyOf': [
                {'type': 'number'},
                {'type': 'string'},
                {'type': 'boolean'}
            ],
            'x-help': 'FlexValue enables dynamic configuration using Home Assistant entities. '
                      'Instead of hardcoding values, reference HA entities that can change at '
                      'runtime. System automatically detects and resolves entity IDs.',
        }

    @model_validator(mode='before')
    @classmethod
    def parse_from_literal(cls, v: Any) -> Any:
        """Wrap a bare literal (int/float/str/bool) into dict form accepted by the model."""
        if not isinstance(v, dict):
            return {'value': v}
        return v

    @staticmethod
    def is_entity_id(value: Any) -> bool:
        """Return True if *value* looks like a Home Assistant entity ID (``domain.object_id``).

        Uses a strict pattern — domain must start with a letter — so numeric strings
        like ``"0.45"`` are never falsely treated as entity IDs.
        """
        return isinstance(value, str) and bool(_HA_ENTITY_ID_RE.match(value))

    def resolve(self, ha_state_getter: callable) -> Any:
        """
        Resolve to the final value.

        The return type is determined by ``_resolve_type`` declared on the class
        (``float`` on the base, overridden to ``int`` / ``bool`` on subclasses).

        If ``value`` is a HA entity ID (``domain.name`` pattern), calls
        ``ha_state_getter(entity_id)`` — which must return the state as a string —
        and converts the result to the class's resolve type.

        For literal values the stored value is returned directly (cast to the
        resolve type if necessary).

        Args:
            ha_state_getter: Callable ``(entity_id: str) -> str`` that returns the
                current HA state for an entity.  The caller is responsible for wiring
                this to the AppDaemon ``self.get_state(eid).state`` call (or a test
                mock).  It is **always required** — pass a no-op mock in tests where
                you know the value is literal.

        Returns:
            The resolved value cast to the class's ``_resolve_type``.
            For bare ``FlexValue`` (``_resolve_type is Any``) no coercion is applied.
        """
        target_type = self._resolve_type

        if self.is_entity_id(self.value):
            state_value = ha_state_getter(self.value)
            if target_type is Any:
                return state_value
            elif target_type == bool:
                return _bool_adapter.validate_python(state_value)
            elif target_type == int:
                return int(float(state_value))  # handle "95.0" → 95
            elif target_type == float:
                return float(state_value)
            else:
                return str(state_value)
        else:
            if target_type is Any:
                return self.value
            elif target_type == bool:
                return _bool_adapter.validate_python(self.value)
            elif target_type == int and not isinstance(self.value, int):
                return int(self.value)
            elif target_type == float and not isinstance(self.value, (int, float)):
                return float(self.value)
            elif target_type == str and not isinstance(self.value, str):
                return str(self.value)
            return self.value


class FlexFloat(FlexValue):
    """FlexValue that resolves to ``float``.

    Use for numeric fields that may alternatively be backed by a HA sensor entity.
    """

    _resolve_type: ClassVar[type] = float


class FlexInt(FlexValue):
    """FlexValue that resolves to ``int``.

    Float literals are silently truncated (e.g. ``1.5 → 1``).
    Use for integer fields such as SOC percentages.
    """

    _resolve_type: ClassVar[type] = int


class FlexBool(FlexValue):
    """FlexValue that resolves to ``bool``.

    Uses Pydantic's lax bool coercion so entity states such as ``"on"``,
    ``"true"``, ``"1"`` all resolve to ``True``.
    Use for boolean fields such as three-phase charging flags.
    """

    _resolve_type: ClassVar[type] = bool


class FlexStr(FlexValue):
    """FlexValue that resolves to ``str``.

    The stored value is returned as-is if it is already a string, or converted
    via ``str()`` for numeric literals.
    Use for fields that accept either a plain string or a HA entity whose state
    is a string (e.g. mode selectors, text sensors).
    """

    _resolve_type: ClassVar[type] = str


class FlexEnum(FlexValue):
    """FlexValue that resolves to ``str`` with enum constraints.
    
    Like FlexStr, but validates that non-entity values match allowed enum options.
    Use for fields with predefined choices OR entity IDs.
    
    Usage:
        strategy: FlexEnum = Field(
            default=FlexEnum(
                value="minimize cost",
                enum_values=["minimize cost", "minimize consumption"]
            ),
            json_schema_extra={"x-enum-values": ["minimize cost", "minimize consumption"]}
        )
    
    For automatic injection of enum_values from field metadata, inherit from
    DAOConfigBaseModel in your configuration model (see below).
    
    Examples:
        FlexEnum(value="minimize cost", enum_values=[...])      # Valid if in list
        FlexEnum(value="sensor.strategy_mode", enum_values=[...])  # Valid entity ID
    """
    
    _resolve_type: ClassVar[type] = str
    enum_values: Optional[list[str]] = Field(default=None, exclude=True)
    
    @model_validator(mode='after')
    def validate_enum_value(self):
        """Validate that value is either an entity ID or in the allowed enum values."""
        # Always allow entity IDs
        if self.is_entity_id(self.value):
            return self
        
        # If enum_values specified, validate against them
        if self.enum_values is not None and self.value not in self.enum_values:
            allowed = ', '.join(f"'{val}'" for val in self.enum_values)
            raise ValueError(
                f"Value '{self.value}' is not valid. Must be one of: {allowed}, "
                f"or a Home Assistant entity ID (e.g., 'input_select.strategy')"
            )
        
        return self
    
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        # Note: This generates the base schema. Enum values are added via
        # json_schema_extra at the Field level, not here at class level.
        return {
            'anyOf': [{'type': 'string'}],  # Accept any string (enum values added by Field)
            'x-help': 'Select from predefined values or use Home Assistant entity ID. '
                      'Entity IDs are always valid.',
        }


class DAOConfigBaseModel(BaseModel):
    """Base model for Day Ahead Optimizer configuration classes.
    
    Provides common validation and preprocessing logic for all DAO configuration models:
    - Automatic enum_values injection for FlexEnum fields from json_schema_extra
    - Future: additional DAO-specific validation and processing logic
    
    All DAO configuration models should inherit from this instead of BaseModel directly.
    
    Example:
        class MyConfig(DAOConfigBaseModel):
            strategy: FlexEnum = Field(
                default=FlexEnum(value="minimize cost"),
                json_schema_extra={"x-enum-values": ["minimize cost", "minimize consumption"]}
            )
    """
    
    @model_validator(mode='before')
    @classmethod
    def inject_flex_enum_values(cls, data):
        """Automatically inject enum_values for all FlexEnum fields from their metadata."""
        if not isinstance(data, dict):
            return data
        
        # Iterate through all fields in the model
        for field_name, field_info in cls.model_fields.items():
            # Check if this field is annotated as FlexEnum
            if field_info.annotation == FlexEnum and field_name in data:
                # Extract enum values from field metadata
                if field_info.json_schema_extra:
                    enum_values = field_info.json_schema_extra.get('x-enum-values')
                    if enum_values:
                        value = data[field_name]
                        # Inject enum_values into the data
                        if isinstance(value, str):
                            data[field_name] = {'value': value, 'enum_values': enum_values}
                        elif isinstance(value, dict) and 'enum_values' not in value:
                            value['enum_values'] = enum_values
        
        return data


class SecretStr(str):
    """
    A secret string reference that gets resolved from secrets.json.
    
    Subclasses ``str`` so it is usable everywhere a plain string is expected.
    Stores the value as-is: either "!secret key_name" for secret references,
    or a plain string value for non-secrets.
    
    Example in options.json:
        {"db_password": "!secret db_password"}
        
    Gets resolved to actual value from secrets.json:
        {"db_password": "my_actual_password_123"}
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return _core_schema.no_info_after_validator_function(
            cls._validate,
            _core_schema.str_schema(),
            ref='SecretStr',
        )

    @classmethod
    def _validate(cls, v: str) -> 'SecretStr':
        """Accept any string value."""
        if not isinstance(v, str):
            raise ValueError(f"SecretStr must be a string, got {type(v)}")
        return cls(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'type': 'string',
            'x-help': 'Secret reference or plain string. Use "!secret key_name" format to '
                      'reference secrets from secrets.json. Plain strings are also accepted.',
        }

    def is_secret_reference(self) -> bool:
        """Return True if this is a secret reference (starts with !secret)."""
        return self.startswith('!secret ')

    def get_secret_key(self) -> str:
        """Extract the secret key name if this is a secret reference, otherwise return self."""
        if self.is_secret_reference():
            return self.replace('!secret ', '', 1).strip()
        return str(self)

    def resolve(self, secrets: dict[str, str]) -> str:
        """
        Resolve the secret to its actual value.

        If the value starts with ``!secret``, extracts the key and looks it up
        in *secrets*. If the key exists, returns the corresponding value.
        Otherwise treats the key as a literal plain-text value and returns it.
        
        For non-secret values (plain strings), returns the value as-is.
        
        Args:
            secrets: Dictionary of secrets loaded from secrets.json
            
        Returns:
            The resolved secret value, or the raw value if not a secret reference.
        """
        if not self.is_secret_reference():
            # Plain string value - return as-is
            return str(self)
        
        # Extract the key from "!secret key_name"
        key = self.get_secret_key()
        
        # Look up in secrets dict, fallback to the key itself if not found
        return secrets.get(key, key)
