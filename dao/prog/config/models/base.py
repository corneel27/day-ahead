"""
Base models and utilities for Pydantic configuration.

This module provides:
- FlexValue: Support for values that can be literals OR Home Assistant entity IDs
- SecretStr: Secure handling of secrets loaded from secrets.json
- Base configuration utilities
"""

from typing import Any, Union
from pydantic import BaseModel, Field, field_validator, ValidationInfo, ConfigDict


class FlexValue(BaseModel):
    """
    A flexible value that can be either a literal or a Home Assistant entity ID.
    
    Supports all HA entity types: int, float, str, bool
    
    Examples:
        FlexValue(value=95)                    # Literal integer
        FlexValue(value="sensor.battery_soc")  # HA entity ID
        FlexValue(value=True)                  # Literal boolean
        FlexValue(value="binary_sensor.grid")  # HA entity ID
    """
    
    value: Union[int, float, str, bool] = Field(
        json_schema_extra={
            "x-help": "Value can be a literal (number, boolean) OR a Home Assistant entity ID for dynamic runtime resolution. Entity IDs detected by presence of '.' (e.g., 'sensor.name').",
            "x-category": "advanced"
        }
    )
    is_entity: bool = Field(
        default=False,
        description="True if value is a HA entity ID",
        json_schema_extra={
            "x-help": "Automatically set to true if value contains '.' (entity ID pattern). Used internally to determine resolution strategy.",
            "x-category": "expert"
        }
    )
    
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'x-help': '''FlexValue enables dynamic configuration using Home Assistant entities. Instead of hardcoding values, reference HA entities that can change at runtime. System automatically detects and resolves entity IDs.''',
            'x-category': 'utility'
        }
    )
    
    @field_validator('value', mode='after')
    @classmethod
    def detect_entity_id(cls, v: Any, info: ValidationInfo) -> Any:
        """Automatically detect if value looks like a HA entity ID."""
        if isinstance(v, str) and '.' in v:
            # Looks like entity_id (e.g., "sensor.temperature")
            # Mark it for runtime resolution
            return v
        return v
    
    @staticmethod
    def is_entity_id(value: Any) -> bool:
        """Check if a value looks like a Home Assistant entity ID."""
        return isinstance(value, str) and '.' in value and not value.startswith('/')
    
    def resolve(self, ha_state_getter: callable, target_type: type = float) -> Any:
        """
        Resolve the flex value to its actual value.
        
        Args:
            ha_state_getter: Function that takes entity_id and returns state value
            target_type: Expected type (int, float, str, bool) for conversion
            
        Returns:
            The resolved value with proper type conversion
        """
        if self.is_entity_id(self.value):
            # Get value from Home Assistant
            state_value = ha_state_getter(self.value)
            # Convert to target type
            if target_type == bool:
                return state_value.lower() in ('true', 'on', '1') if isinstance(state_value, str) else bool(state_value)
            elif target_type == int:
                return int(float(state_value))  # Handle "95.0" -> 95
            elif target_type == float:
                return float(state_value)
            else:  # str
                return str(state_value)
        else:
            # Use literal value, ensure type
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
            "x-category": "security",
            "x-validation-hint": "Use format: !secret key_name"
        }
    )
    
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'x-help': '''SecretStr provides secure secret management. Secrets stored in separate secrets.json file, never in main config. Reference format: "!secret key_name". Essential for passwords, API tokens, and sensitive data.''',
            'x-category': 'utility'
        }
    )
    
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
        
        Args:
            secrets: Dictionary of secrets loaded from secrets.json
            
        Returns:
            The actual secret value
            
        Raises:
            KeyError: If secret key not found in secrets
        """
        if self.secret_key not in secrets:
            raise KeyError(
                f"Secret '{self.secret_key}' not found in secrets.json. "
                f"Available secrets: {', '.join(secrets.keys())}"
            )
        return secrets[self.secret_key]
