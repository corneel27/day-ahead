"""
Error handling utilities and handlers for API v2

Provides standardized error response format and handlers for common exceptions.
Keep implementation isolated from old code.
"""

import json
import logging
from flask import jsonify
from pydantic import ValidationError
from dao.prog.config.loader import ConfigValidationError
from dao.webserver.app.api_v2 import api_v2_bp

logger = logging.getLogger(__name__)


def error_response(message: str, errors: list = None, status_code: int = 400):
    """
    Create standardized error response
    
    Args:
        message: Human-readable error message
        errors: List of error details (strings or dicts)
        status_code: HTTP status code
        
    Returns:
        Tuple of (jsonified response, status_code)
    """
    return jsonify({
        "error": message,
        "details": errors or [],
        "status": status_code
    }), status_code


@api_v2_bp.errorhandler(ConfigValidationError)
def handle_config_validation_error(e):
    """
    Handle ConfigValidationError from ConfigurationLoader
    
    Parses validation errors and returns structured response.
    """
    logger.error(f"Configuration validation error: {e}")
    
    # Parse error message into lines
    error_lines = str(e).split('\n')
    
    return error_response(
        message="Configuration validation failed",
        errors=error_lines,
        status_code=400
    )


@api_v2_bp.errorhandler(ValidationError)
def handle_pydantic_validation_error(e):
    """
    Handle Pydantic ValidationError
    
    Formats Pydantic errors into structured field-level errors.
    """
    logger.error(f"Pydantic validation error: {e}")
    
    # Format Pydantic errors with field paths
    error_details = []
    for err in e.errors():
        # Build field path (e.g., "batteries.0.name")
        path = " → ".join(str(p) for p in err["loc"])
        error_details.append({
            "field": path,
            "message": err["msg"],
            "type": err["type"]
        })
    
    return error_response(
        message="Configuration validation failed",
        errors=error_details,
        status_code=400
    )


@api_v2_bp.errorhandler(ValueError)
def handle_value_error(e):
    """
    Handle ValueError exceptions
    
    Used for simple validation failures (e.g., from save_secrets).
    """
    logger.error(f"Value error: {e}")
    
    return error_response(
        message="Invalid value",
        errors=[str(e)],
        status_code=400
    )


@api_v2_bp.errorhandler(FileNotFoundError)
def handle_file_not_found(e):
    """
    Handle FileNotFoundError exceptions
    
    Returns 404 when config or secrets files don't exist.
    """
    logger.error(f"File not found: {e}")
    
    return error_response(
        message="File not found",
        errors=[str(e)],
        status_code=404
    )


@api_v2_bp.errorhandler(json.JSONDecodeError)
def handle_json_decode_error(e):
    """
    Handle JSONDecodeError exceptions
    
    Returns 500 when JSON files are malformed.
    """
    logger.error(f"Invalid JSON: {e}")
    
    return error_response(
        message="Invalid JSON in file",
        errors=[str(e)],
        status_code=500
    )


@api_v2_bp.errorhandler(500)
def handle_internal_error(e):
    """
    Handle internal server errors (500)
    
    Catches unexpected exceptions.
    """
    logger.error(f"Internal server error: {e}", exc_info=True)
    
    return error_response(
        message="Internal server error",
        errors=[str(e)],
        status_code=500
    )
