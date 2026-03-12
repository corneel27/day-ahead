"""
Base models and utilities for Pydantic configuration.

This module provides:
- FlexValue: Support for values that can be literals OR Home Assistant entity IDs
- SecretStr: Secure handling of secrets loaded from secrets.json
- Base configuration utilities
"""

import re
from typing import Any, Union
from pydantic import BaseModel, Field, field_validator, model_serializer, model_validator, ValidationInfo, ConfigDict

# Matches Home Assistant entity IDs: "domain.object_id"
# domain must start with a letter (rules out numeric strings like "0.45")
_HA_ENTITY_ID_RE = re.compile(r'^[a-z_][a-z0-9_]*\.[a-z0-9_]+$')


class FlexValue(BaseModel):
    """
    A flexible value that can be either a literal or a Home Assistant entity ID.

    Accepts bare literals in config (e.g. ``95``, ``0.5``, ``"sensor.battery_soc"``)
    and wraps them automatically.  At runtime call ``resolve()`` to get the final
    value — either the stored literal or a live HA state lookup.

    Examples:
        FlexValue(value=95)                    # Literal integer
        FlexValue(value="sensor.battery_soc")  # HA entity ID — resolved at runtime
        FlexValue(value=True)                  # Literal boolean
        FlexValue(value="binary_sensor.grid")  # HA entity ID — resolved at runtime
    """

    value: Union[int, float, str, bool] = Field(
        json_schema_extra={
            "x-help": "Value can be a literal (number, boolean) OR a Home Assistant entity ID for dynamic runtime resolution. Entity IDs detected by presence of '.' (e.g., 'sensor.name').",
            "x-ui-section": "General"
        }
    )

    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'x-help': '''FlexValue enables dynamic configuration using Home Assistant entities. Instead of hardcoding values, reference HA entities that can change at runtime. System automatically detects and resolves entity IDs.'''
        }
    )

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

    def resolve(self, ha_state_getter: callable, target_type: type = float) -> Any:
        """
        Resolve to the final value.

        If ``value`` is a HA entity ID (``domain.name`` pattern), calls
        ``ha_state_getter(entity_id)`` — which must return the state as a string —
        and converts the result to ``target_type``.

        For literal values the stored value is returned directly (with a cast to
        ``target_type`` if necessary).

        Args:
            ha_state_getter: Callable ``(entity_id: str) -> str`` that returns the
                current HA state for an entity.  The caller is responsible for wiring
                this to the AppDaemon ``self.get_state(eid).state`` call (or a test
                mock).  It is **always required** — pass a no-op mock in tests where
                you know the value is literal.
            target_type: Desired Python type for the returned value (``int``,
                ``float``, ``str``, or ``bool``).  Defaults to ``float``.

        Returns:
            The resolved value cast to *target_type*.
        """
        if self.is_entity_id(self.value):
            state_value = ha_state_getter(self.value)
            if target_type == bool:
                return state_value.lower() in ('true', 'on', '1') if isinstance(state_value, str) else bool(state_value)
            elif target_type == int:
                return int(float(state_value))  # handle "95.0" → 95
            elif target_type == float:
                return float(state_value)
            else:
                return str(state_value)
        else:
            if target_type == bool and not isinstance(self.value, bool):
                return bool(self.value)
            elif target_type == int and not isinstance(self.value, int):
                return int(self.value)
            elif target_type == float and not isinstance(self.value, (int, float)):
                return float(self.value)
            return self.value


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
            key = v.replace('!secret ', '', 1).strip() if v.startswith('!secret ') else v
            return {'secret_key': key}
        return v

    @field_validator('secret_key', mode='before')
    @classmethod
    def parse_secret_reference(cls, v: Any, info: ValidationInfo) -> str:
        """Parse secret reference from '!secret key_name' format."""
        if isinstance(v, str):
            if v.startswith('!secret '):
                return v.replace('!secret ', '', 1).strip()
            # Direct secret key (already resolved)
            return v
        raise ValueError(f"Secret must be string, got {type(v)}")
    
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
        """Always serializes back to '!secret key_name' — never the resolved value."""
        return f"!secret {self.secret_key}"
