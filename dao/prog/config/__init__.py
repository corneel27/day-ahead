"""
Pydantic-based configuration management for Day Ahead Optimizer.

This package provides:
- Type-safe configuration models
- Automatic validation
- Secret resolution
- Flex settings (literal values or HA entity IDs)
- Configuration versioning and migration
- JSON schema generation
"""

from .loader import ConfigurationLoader
from .models.base import FlexValue, SecretStr

__all__ = [
    "ConfigurationLoader",
    "FlexValue",
    "SecretStr",
]
