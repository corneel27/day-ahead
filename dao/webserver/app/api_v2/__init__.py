"""
API v2 Blueprint for Day Ahead Optimizer

This module provides the v2 API endpoints for configuration management,
secrets management, and HA proxy functionality.

Keep this module isolated from existing code for clean separation.
"""

import logging
import time
from flask import Blueprint, request, g

# Set up logger for API v2
logger = logging.getLogger(__name__)

# Create API v2 Blueprint
api_v2_bp = Blueprint('api_v2', __name__)


# Request logging middleware
@api_v2_bp.before_request
def before_request():
    """Record request start time for duration calculation"""
    g.start_time = time.time()


@api_v2_bp.after_request
def after_request(response):
    """
    Log all API v2 requests with method, path, status code, and duration.
    Uses INFO level for reads (GET), WARNING level for writes (POST, PUT, DELETE).
    """
    # Calculate request duration
    duration_ms = 0
    if hasattr(g, 'start_time'):
        duration_ms = (time.time() - g.start_time) * 1000
    
    # Determine log level based on HTTP method
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO
    
    # Log request (never log sensitive data like tokens or secrets)
    logger.log(
        log_level,
        f"{request.method} {request.path} - {response.status_code} - {duration_ms:.2f}ms"
    )
    
    return response


# Import routes after blueprint creation to avoid circular imports
from . import config
from . import ha_proxy
from . import errors
