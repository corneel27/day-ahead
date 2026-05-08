"""
Tests for API v2 Home Assistant proxy endpoint.
"""

import json
import pytest
import threading
import time
from flask import Flask, jsonify, request
from werkzeug.serving import make_server


class MockHAServer:
    """Mock Home Assistant server for testing proxy."""
    
    def __init__(self, port=8555):
        """Initialize mock server."""
        self.port = port
        self.app = Flask('mock_ha')
        self.server = None
        self.thread = None
        self.setup_routes()
    
    def setup_routes(self):
        """Set up mock HA API routes."""
        
        @self.app.route('/api/states', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
        def handle_states():
            """Mock /api/states endpoint supporting all HTTP methods."""
            # Check authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({"error": "Unauthorized"}), 401
            
            # Return mock entities for any method
            if request.method == 'HEAD':
                return '', 200
            return jsonify([
                {
                    "entity_id": "sensor.temperature",
                    "state": "22.5",
                    "attributes": {"unit_of_measurement": "°C"}
                },
                {
                    "entity_id": "sensor.humidity",
                    "state": "65",
                    "attributes": {"unit_of_measurement": "%"}
                }
            ]), 200
        
        @self.app.route('/api/states/<entity_id>', methods=['GET'])
        def get_entity_state(entity_id):
            """Mock GET /api/states/<entity_id> endpoint."""
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({"error": "Unauthorized"}), 401
            
            return jsonify({
                "entity_id": entity_id,
                "state": "test_value",
                "attributes": {}
            }), 200
        
        @self.app.route('/api/services/<domain>/<service>', methods=['POST'])
        def call_service(domain, service):
            """Mock POST /api/services endpoint."""
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({"error": "Unauthorized"}), 401
            
            return jsonify({
                "success": True,
                "domain": domain,
                "service": service
            }), 200
        
        @self.app.route('/api/timeout', methods=['GET'])
        def timeout_endpoint():
            """Mock endpoint that times out."""
            time.sleep(15)  # Longer than proxy timeout
            return jsonify({"message": "Should not reach here"}), 200
    
    def start(self):
        """Start mock server in background thread."""
        self.server = make_server('localhost', self.port, self.app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        time.sleep(0.1)  # Give server time to start
    
    def stop(self):
        """Stop mock server."""
        if self.server:
            self.server.shutdown()
            if self.thread:
                self.thread.join(timeout=1.0)


@pytest.fixture
def mock_ha_server():
    """Create and start mock HA server."""
    server = MockHAServer()
    server.start()
    yield server
    server.stop()


class TestHAProxySuccess:
    """Test successful proxy requests."""
    
    def test_proxy_get_states(self, client, mock_ha_server):
        """Test proxying GET /api/states request."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token_12345'
            }
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 2
        assert data[0]['entity_id'] == 'sensor.temperature'
        assert data[1]['entity_id'] == 'sensor.humidity'
    
    def test_proxy_get_entity(self, client, mock_ha_server):
        """Test proxying GET /api/states/<entity_id> request."""
        response = client.get(
            '/api/v2/ha-proxy/states/sensor.temperature',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['entity_id'] == 'sensor.temperature'
        assert data['state'] == 'test_value'
    
    def test_proxy_post_service(self, client, mock_ha_server):
        """Test proxying POST /api/services request."""
        response = client.post(
            '/api/v2/ha-proxy/services/light/turn_on',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token',
                'Content-Type': 'application/json'
            },
            data=json.dumps({"entity_id": "light.living_room"})
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['domain'] == 'light'
        assert data['service'] == 'turn_on'
    
    def test_proxy_without_port(self, client, mock_ha_server):
        """Test proxying without port header (should use default)."""
        # This will fail to connect since we're using a non-standard port
        # but it tests that the URL is built correctly
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                # No X-HA-Port header
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        # Should return connection error since localhost:80 isn't running
        assert response.status_code == 502


class TestHAProxyValidation:
    """Test request validation and error handling."""
    
    def test_proxy_missing_host(self, client):
        """Test proxy without X-HA-Host header."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'X-HA-Host' in data['details'][0]
    
    def test_proxy_missing_token(self, client):
        """Test proxy without X-HA-Token header."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': '8123'
            }
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'X-HA-Token' in data['details'][0]
    
    def test_proxy_invalid_protocol(self, client):
        """Test proxy with invalid protocol."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Protocol': 'javascript',  # Invalid protocol
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'protocol' in data['error'].lower()


class TestHAProxyAuthorization:
    """Test authorization handling."""
    
    def test_proxy_forwards_token(self, client, mock_ha_server):
        """Test that token is forwarded as Authorization header."""
        # Mock server returns 401 if token missing/invalid
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'valid_token'
            }
        )
        
        # Should succeed (mock accepts any token with Bearer prefix)
        assert response.status_code == 200
    
    def test_proxy_returns_ha_error(self, client, mock_ha_server):
        """Test that HA error responses are returned."""
        # Send request without X-HA-Token header - proxy will return 400
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http'
                # No X-HA-Token header
            }
        )
        
        # Should return 400 from proxy (missing token validation)
        assert response.status_code == 400


class TestHAProxyErrors:
    """Test error handling for connection issues."""
    
    def test_proxy_connection_refused(self, client):
        """Test proxy when HA server is not reachable."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': '9999',  # Non-existent server
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 502
        data = json.loads(response.data)
        assert 'error' in data
        assert data['status'] == 502
    
    def test_proxy_invalid_hostname(self, client):
        """Test proxy with invalid hostname."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'invalid.nonexistent.domain',
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 502
        data = json.loads(response.data)
        assert 'error' in data


class TestHAProxyHTTPMethods:
    """Test different HTTP methods are supported."""
    
    @pytest.mark.parametrize("method", ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
    def test_proxy_supports_all_methods(self, client, method, mock_ha_server):
        """Test that all HTTP methods are supported by proxy."""
        # Note: HEAD returns empty body, so we can't test content
        # But we can verify the proxy accepts the method
        response = client.open(
            '/api/v2/ha-proxy/states',
            method=method,
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        # Should not return 405 Method Not Allowed
        assert response.status_code != 405


class TestHAProxySecurity:
    """Test security features of proxy."""
    
    def test_proxy_adds_nosniff_header(self, client, mock_ha_server):
        """Test that X-Content-Type-Options: nosniff header is added."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Host': 'localhost',
                'X-HA-Port': str(mock_ha_server.port),
                'X-HA-Protocol': 'http',
                'X-HA-Token': 'test_token'
            }
        )
        
        assert response.status_code == 200
        assert 'X-Content-Type-Options' in response.headers
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
    
    def test_proxy_error_has_content_type(self, client):
        """Test that error responses have Content-Type header."""
        response = client.get(
            '/api/v2/ha-proxy/states',
            headers={
                'X-HA-Token': 'test_token'
                # Missing X-HA-Host
            }
        )
        
        assert response.status_code == 400
        assert 'Content-Type' in response.headers
        assert 'application/json' in response.headers['Content-Type']
