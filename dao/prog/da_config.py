# Legacy da_config.py - now using Pydantic-based configuration
# This file provides backward-compatible Config class for seamless migration

from dao.prog.config.wrapper import Config, get_config

# Re-export for backward compatibility
__all__ = ['Config', 'get_config']
