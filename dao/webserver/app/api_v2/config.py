"""
Configuration, Secrets, and Schema API endpoints for Day Ahead Optimizer

Endpoints:
- GET/POST /api/v2/config - Load and save configuration
- GET/POST /api/v2/secrets - Load and save secrets
- GET /api/v2/config/schema - Get JSON schema
- GET /api/v2/config/uischema - Get UI schema

Keep implementation isolated from old code.
"""

import json
import logging
from pathlib import Path
from flask import request, jsonify
from pydantic import ValidationError

from dao.webserver.app.api_v2 import api_v2_bp
from dao.prog.config.loader import ConfigurationLoader, ConfigValidationError

logger = logging.getLogger(__name__)

# Path to config files (same as used by existing code)
CONFIG_PATH = Path("app/static/data/options.json")
SECRETS_PATH = Path("app/static/data/secrets.json")

# Path to generated schemas
SCHEMA_DIR = Path("app/static/schemas")
SCHEMA_PATH = SCHEMA_DIR / "schema.json"
UISCHEMA_PATH = SCHEMA_DIR / "uischema.json"


# ============================================================================
# Configuration Endpoints
# ============================================================================

@api_v2_bp.route('/config', methods=['GET'])
def get_config():
    """
    Load configuration from options.json
    Returns config with !secret references intact (not resolved)
    """
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found: {CONFIG_PATH}")
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")
    
    # Read configuration file directly (no validation needed for reads)
    # JSONDecodeError will be caught by error handler
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    
    logger.info("Configuration loaded successfully")
    return jsonify(config_data), 200


@api_v2_bp.route('/config', methods=['POST'])
def save_config():
    """
    Save configuration to options.json
    Validates config before saving
    """
    # Get JSON body
    config_data = request.get_json()
    if not config_data:
        raise ValueError("No configuration data provided")
    
    # Load existing loader to get raw options for unknown key preservation
    loader = ConfigurationLoader(CONFIG_PATH)
    
    # Validate new config (ValidationError/ConfigValidationError will be caught by handlers)
    from dao.prog.config.loader import VERSION_MODELS, CURRENT_VERSION
    version = config_data.get('config_version', CURRENT_VERSION)
    model_class = VERSION_MODELS.get(version, VERSION_MODELS[CURRENT_VERSION])
    
    # Validate with Pydantic (raises ValidationError if invalid)
    validated_config = model_class(**config_data)
    
    # Save using loader (with file locking)
    loader.save(validated_config.model_dump(mode='json', exclude_none=True))
    
    logger.info("Configuration saved successfully")
    return jsonify({
        "message": "Configuration saved successfully",
        "status": 200
    }), 200


# ============================================================================
# Secrets Endpoints
# ============================================================================

@api_v2_bp.route('/secrets', methods=['GET'])
def get_secrets():
    """
    Load secrets from secrets.json
    Returns all secrets with actual values (NOT masked)
    """
    if not SECRETS_PATH.exists():
        logger.info(f"Secrets file not found, returning empty dict")
        return jsonify({}), 200
    
    # Read secrets file directly (JSONDecodeError will be caught by handler)
    with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
        secrets = json.load(f)
    
    logger.info(f"Loaded {len(secrets)} secrets (values not logged)")
    return jsonify(secrets), 200


@api_v2_bp.route('/secrets', methods=['POST'])
def save_secrets():
    """
    Save secrets to secrets.json
    Uses ConfigurationLoader.save_secrets() for atomic save with file locking
    """
    # Get JSON body
    secrets_data = request.get_json()
    if secrets_data is None:
        raise ValueError("No secrets data provided")
    
    # Use ConfigurationLoader for atomic save with file locking
    # ValueError from validation will be caught by error handler
    loader = ConfigurationLoader(CONFIG_PATH, SECRETS_PATH)
    loader.save_secrets(secrets_data)
    
    return jsonify({
        "message": "Secrets saved successfully",
        "status": 200
    }), 200


# ============================================================================
# Schema Endpoints
# ============================================================================

@api_v2_bp.route('/config/schema', methods=['GET'])
def get_schema():
    """
    Return JSON schema for configuration
    """
    if not SCHEMA_PATH.exists():
        logger.error(f"Schema file not found: {SCHEMA_PATH}")
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}. Please generate schemas first.")
    
    # Read schema file (JSONDecodeError will be caught by handler)
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    logger.info(f"Loaded schema from {SCHEMA_PATH}")
    return jsonify(schema), 200


@api_v2_bp.route('/config/uischema', methods=['GET'])
def get_uischema():
    """
    Return UI schema for configuration
    """
    if not UISCHEMA_PATH.exists():
        logger.error(f"UISchema file not found: {UISCHEMA_PATH}")
        raise FileNotFoundError(f"UISchema file not found at {UISCHEMA_PATH}. Please generate schemas first.")
    
    # Read UISchema file (JSONDecodeError will be caught by handler)
    with open(UISCHEMA_PATH, 'r', encoding='utf-8') as f:
        uischema = json.load(f)
    
    logger.info(f"Loaded UISchema from {UISCHEMA_PATH}")
    return jsonify(uischema), 200
