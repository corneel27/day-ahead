"""
Pytest configuration for webserver tests.

This file provides fixtures and configuration needed for testing the Flask app.
"""

import pytest
import os
import json
import sys
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Set up test environment before any tests run.
    
    This creates minimal config files needed for app initialization.
    Changes to webserver directory so relative paths work correctly.
    """
    # Save original directory
    original_dir = Path.cwd()
    
    # Change to webserver directory (where da_server.py runs from)
    webserver_dir = original_dir / "webserver"
    os.chdir(webserver_dir)
    
    # Create data directory if it doesn't exist
    data_dir = Path("app/static/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create minimal options.json if it doesn't exist
    options_path = data_dir / "options.json"
    if not options_path.exists():
        # Use unversioned config (auto-migrates to V0)
        minimal_config = {
            "homeassistant": {
                "protocol api": "http",
                "ip adress": "localhost",
                "ip port": 8123,
                "token": "!secret ha_token"
            },
            "database da": {
                "engine": "sqlite",
                "db_path": "../data"
            },
            "database ha": {
                "engine": "sqlite",
                "database": "home-assistant_v2.db",
                "db_path": "../data"
            },
            "meteoserver-key": "!secret meteoserver-key",
            "solar": [],
            "batteries": []
        }
        with open(options_path, 'w') as f:
            json.dump(minimal_config, f, indent=2)
    
    # Create minimal secrets.json if it doesn't exist
    secrets_path = data_dir / "secrets.json"
    if not secrets_path.exists():
        with open(secrets_path, 'w') as f:
            json.dump({"ha_token": "test_token"}, f)
    
    yield
    
    # Restore original directory
    os.chdir(original_dir)


@pytest.fixture
def app():
    """
    Create Flask app for testing.
    
    Note: Import happens inside the fixture to ensure
    setup_test_environment runs first.
    """
    from dao.webserver.app import app
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    with app.test_client() as client:
        yield client
