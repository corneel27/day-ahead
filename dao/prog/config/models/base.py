"""
Base models and utilities for Pydantic configuration.

This module provides:
- FlexValue: Base class for values that can be literals OR Home Assistant entity IDs
- FlexFloat / FlexInt / FlexBool: Typed variants — same flex behaviour, typed resolve()
- SecretStr: Secure handling of secrets loaded from secrets.json
- Base configuration utilities
"""

import re
from typing import Any, ClassVar, Union
from pydantic import BaseModel, Field, TypeAdapter, model_serializer, model_validator, field_validator, ConfigDict

# Matches Home Assistant entity IDs: "domain.object_id"
# domain must start with a letter (rules out numeric strings like "0.45")
_HA_ENTITY_ID_RE = re.compile(r'^[a-z_][a-z0-9_]*\.[a-z0-9_]+$')

# Re-use a single TypeAdapter for bool coercion — Pydantic's lax bool validator
# accepts "true"/"false", "1"/"0", "on"/"off", "yes"/"no", integers, etc.
_bool_adapter = TypeAdapter(bool)


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

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'anyOf': [{'type': 'number'}, {'type': 'string'}],
            'x-help': 'Numeric value or Home Assistant entity ID. '
                      'Entity state is resolved to a float at runtime.',
        }


class FlexInt(FlexValue):
    """FlexValue that resolves to ``int``.

    Float literals are silently truncated (e.g. ``1.5 → 1``).
    Use for integer fields such as SOC percentages.
    """

    _resolve_type: ClassVar[type] = int

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'anyOf': [{'type': 'integer'}, {'type': 'string'}],
            'x-help': 'Integer value or Home Assistant entity ID. '
                      'Entity state is resolved to an integer at runtime.',
        }


class FlexBool(FlexValue):
    """FlexValue that resolves to ``bool``.

    Uses Pydantic's lax bool coercion so entity states such as ``"on"``,
    ``"true"``, ``"1"`` all resolve to ``True``.
    Use for boolean fields such as three-phase charging flags.
    """

    _resolve_type: ClassVar[type] = bool

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'anyOf': [{'type': 'boolean'}, {'type': 'string'}],
            'x-help': 'Boolean value or Home Assistant entity ID. '
                      'Entity state is resolved using Pydantic lax bool coercion '
                      '("on", "true", "1" → True; "off", "false", "0" → False).',
        }


class FlexStr(FlexValue):
    """FlexValue that resolves to ``str``.

    The stored value is returned as-is if it is already a string, or converted
    via ``str()`` for numeric literals.
    Use for fields that accept either a plain string or a HA entity whose state
    is a string (e.g. mode selectors, text sensors).
    """

    _resolve_type: ClassVar[type] = str

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {
            'type': 'string',
            'x-help': 'String value or Home Assistant entity ID. '
                      'Entity state is returned as a plain string at runtime.',
        }


class SecretStr(BaseModel):
    """
    A secret string reference that gets resolved from secrets.json.
    
    Example in options.json:
        {"db_password": "!secret db_password"}
        
    Gets resolved to actual value from secrets.json:
        {"db_password": "my_actual_password_123"}
    """
    
    secret_key: str = Field(
        json_schema_extra={
            "x-help": "Secret key name to resolve from secrets.json. Use '!secret key_name' in config. Never store actual secrets in options.json!",
            "x-ui-section": "General",
            "x-validation-hint": "Use format: !secret key_name"
        }
    )
    
    is_secret: bool = Field(default=False, exclude=True)
    
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'x-help': '''SecretStr provides secure secret management. Secrets stored in separate secrets.json file, never in main config. Reference format: "!secret key_name". Essential for passwords, API tokens, and sensitive data.'''
        }
    )

    @model_validator(mode='before')
    @classmethod
    def parse_from_string(cls, v: Any) -> Any:
        """Accept '!secret key_name' or a plain key name as input, coerce to dict."""
        if isinstance(v, str):
            if v.startswith('!secret '):
                key = v.replace('!secret ', '', 1).strip()
                return {'secret_key': key, 'is_secret': True}
            else:
                return {'secret_key': v, 'is_secret': False}
        return v

    @field_validator('secret_key', mode='before')
    @classmethod
    def parse_secret_key(cls, v: Any) -> Any:
        """Parse secret_key if it's a string starting with !secret."""
        if isinstance(v, str) and v.startswith('!secret '):
            return v.replace('!secret ', '', 1).strip()
        return v

    @model_validator(mode='after')
    def set_is_secret_from_key(self) -> 'SecretStr':
        """Set is_secret based on whether secret_key was parsed from !secret."""
        if isinstance(self.secret_key, str) and self.secret_key.startswith('!secret '):
            # If somehow it wasn't parsed, but shouldn't happen
            self.secret_key = self.secret_key.replace('!secret ', '', 1).strip()
            self.is_secret = True
        elif 'is_secret' not in self.__dict__ or not self.is_secret:
            # If not set, check if it looks like !secret
            pass  # already handled in before
        return self

    def resolve(self, secrets: dict[str, str]) -> str:
        """
        Resolve the secret to its actual value.

        If ``secret_key`` exists in *secrets*, returns the corresponding value.
        Otherwise the key is treated as a literal plain-text value and returned
        as-is, so fields typed as ``SecretStr`` work for both ``!secret`` references
        and plain-text credentials without needing a ``SecretStr | str`` union.
        
        Args:
            secrets: Dictionary of secrets loaded from secrets.json
            
        Returns:
            The resolved secret value, or the raw key if not found in secrets.
        """
        if self.secret_key not in secrets:
            # Not a secrets.json reference — treat as a literal plain-text value
            return self.secret_key
        return secrets[self.secret_key]

    @model_serializer
    def serialize_secret(self) -> str:
        """Serialize back to the original key (or literal) — never the resolved value."""
        if self.is_secret:
            return f'!secret {self.secret_key}'
        else:
            return self.secret_key
