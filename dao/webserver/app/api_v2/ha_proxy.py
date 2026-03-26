"""
Home Assistant Proxy Endpoint for Day Ahead Optimizer

Proxies requests to Home Assistant API using connection details from headers.
Allows frontend to access HA API without hardcoded endpoints.

Keep implementation isolated from old code.
"""

import logging
import requests
from flask import request, Response
from dao.webserver.app.api_v2 import api_v2_bp

logger = logging.getLogger(__name__)

# Timeout for HA requests (seconds)
HA_REQUEST_TIMEOUT = 10


@api_v2_bp.route('/ha-proxy/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def ha_proxy(path):
    """
    Proxy requests to Home Assistant API
    
    Extracts HA connection details from request headers:
    - X-HA-Host: Home Assistant hostname (e.g., "homeassistant.local")
    - X-HA-Port: Home Assistant port (e.g., "8123")
    - X-HA-Protocol: Protocol to use (e.g., "http" or "https")
    - X-HA-Token: Home Assistant long-lived access token
    
    Forwards request to: {protocol}://{host}:{port}/api/{path}
    Returns HA response exactly as-is.
    """
    try:
        # Extract HA connection details from headers
        ha_host = request.headers.get('X-HA-Host')
        ha_port = request.headers.get('X-HA-Port')
        ha_protocol = request.headers.get('X-HA-Protocol', 'http')
        ha_token = request.headers.get('X-HA-Token')
        
        # Validate required headers
        if not ha_host:
            logger.error("Missing X-HA-Host header")
            return {
                "error": "Missing Home Assistant host",
                "details": ["X-HA-Host header is required"],
                "status": 400
            }, 400
        
        if not ha_token:
            logger.error("Missing X-HA-Token header")
            return {
                "error": "Missing Home Assistant token",
                "details": ["X-HA-Token header is required"],
                "status": 400
            }, 400
        
        # Build target URL (prepend /api/ to path)
        port_part = f":{ha_port}" if ha_port else ""
        target_url = f"{ha_protocol}://{ha_host}{port_part}/api/{path}"
        
        # Add query string if present
        if request.query_string:
            target_url += f"?{request.query_string.decode('utf-8')}"
        
        # Prepare headers - only send essential headers to HA
        forward_headers = {
            'Authorization': f"Bearer {ha_token}",
        }
        
        # Forward client headers that affect content negotiation
        for header in ['Content-Type', 'Accept', 'Accept-Encoding']:
            if header in request.headers:
                forward_headers[header] = request.headers[header]
        
        # Log request (never log token)
        logger.info(f"Proxying {request.method} request to HA: {ha_protocol}://{ha_host}{port_part}/api/{path}")
        
        # Forward request to Home Assistant
        # Use stream=True to get raw response without automatic decompression
        try:
            response = requests.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                data=request.get_data(),
                timeout=HA_REQUEST_TIMEOUT,
                allow_redirects=False,
                verify=True,  # Verify SSL certificates
                stream=True   # Don't decompress, get raw response
            )
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to Home Assistant at {ha_host}")
            return {
                "error": "Home Assistant request timeout",
                "details": [f"Request to {ha_host} timed out after {HA_REQUEST_TIMEOUT} seconds"],
                "status": 504
            }, 504
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Home Assistant at {ha_host}: {e}")
            return {
                "error": "Cannot connect to Home Assistant",
                "details": [f"Connection to {ha_host}{port_part} failed. Check host, port, and network."],
                "status": 502
            }, 502
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL error connecting to Home Assistant: {e}")
            return {
                "error": "SSL certificate verification failed",
                "details": [str(e)],
                "status": 502
            }, 502
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error proxying to Home Assistant: {e}")
            return {
                "error": "Failed to proxy request to Home Assistant",
                "details": [str(e)],
                "status": 502
            }, 502
        
        # Return HA response exactly as-is (raw, with original encoding)
        # Copy all response headers
        response_headers = dict(response.headers)
        
        # Remove headers that shouldn't be forwarded
        for header in ['Transfer-Encoding', 'Connection', 'Keep-Alive']:
            response_headers.pop(header, None)
        
        logger.info(f"HA proxy response: {response.status_code}")
        
        # Check if client accepts compression
        client_accepts_encoding = 'Accept-Encoding' in request.headers
        
        if client_accepts_encoding:
            # Client supports compression - forward raw compressed response
            response.raw.decode_content = False
            raw_content = response.raw.read()
        else:
            # Client doesn't support compression - return decompressed content
            # Remove Content-Encoding since we're decompressing
            response_headers.pop('Content-Encoding', None)
            response_headers.pop('Content-Length', None)
            raw_content = response.content  # requests auto-decompresses
        
        # Create Flask response with same status code, headers, and body
        return Response(
            raw_content,
            status=response.status_code,
            headers=response_headers
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in HA proxy: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "details": [str(e)],
            "status": 500
        }, 500
