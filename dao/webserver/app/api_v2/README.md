# Day Ahead Optimizer - API v2 Documentation

This document describes the RESTful API v2 endpoints for the Day Ahead Optimizer configuration interface.

## Overview

API v2 provides endpoints for:
- **Configuration management** - Load and save optimizer configuration
- **Secrets management** - Manage sensitive credentials separately
- **Schema retrieval** - Get JSON Schema and UI Schema for validation
- **Home Assistant proxy** - Securely proxy requests to HA API

**Base URL:** `/api/v2`

**Content Type:** All endpoints accept and return `application/json`

## Authentication

Currently no authentication is required. The API is designed to run within a Home Assistant addon where access is controlled at the addon level.

## Error Response Format

All errors follow a consistent format:

```json
{
  "error": "Human-readable error message",
  "details": ["Detailed error information", "..."],
  "status": 400
}
```

**Error Status Codes:**
- `400` - Bad Request (validation errors, missing data)
- `404` - Not Found (file or resource doesn't exist)
- `500` - Internal Server Error (unexpected failures)
- `502` - Bad Gateway (HA proxy connection errors)
- `504` - Gateway Timeout (HA request timeout)

## Endpoints

### Configuration Endpoints

#### Get Configuration

Load the current optimizer configuration.

**Request:**
```http
GET /api/v2/config
```

**Response:** `200 OK`
```json
{
  "config_version": 2,
  "general": {
    "time_zone": "Europe/Amsterdam",
    "ha_url": "http://homeassistant.local:8123",
    "ha_token": "!secret ha_token"
  },
  "batteries": [
    {
      "name": "Battery 1",
      "capacity_kwh": 10.0,
      "charge_rate_kw": 5.0,
      "discharge_rate_kw": 5.0
    }
  ],
  ...
}
```

**Notes:**
- Returns raw configuration file contents
- `!secret` references are **NOT** resolved (remain as placeholders)
- File must exist or returns `404`

**Error Responses:**

`404 Not Found` - Configuration file doesn't exist
```json
{
  "error": "File not found",
  "details": ["Configuration file not found: app/static/data/options.json"],
  "status": 404
}
```

---

#### Save Configuration

Save a new configuration. Validates before saving.

**Request:**
```http
POST /api/v2/config
Content-Type: application/json

{
  "config_version": 2,
  "general": { ... },
  "batteries": [ ... ],
  ...
}
```

**Response:** `200 OK`
```json
{
  "message": "Configuration saved successfully",
  "status": 200
}
```

**Validation:**
- Configuration is validated against Pydantic models before saving
- Atomic save with file locking (prevents concurrent write corruption)
- Unknown fields are preserved (allows forward compatibility)

**Error Responses:**

`400 Bad Request` - Validation failed
```json
{
  "error": "Configuration validation failed",
  "details": [
    {
      "field": "batteries → 0 → capacity_kwh",
      "message": "Input should be greater than 0",
      "type": "greater_than"
    }
  ],
  "status": 400
}
```

`400 Bad Request` - No data provided
```json
{
  "error": "Invalid value",
  "details": ["No configuration data provided"],
  "status": 400
}
```

---

### Secrets Endpoints

#### Get Secrets

Load all secrets from secrets file.

**Request:**
```http
GET /api/v2/secrets
```

**Response:** `200 OK`
```json
{
  "ha_token": "eyJ0eXAiOiJKV1QiLC...",
  "solcast_api_key": "abc123xyz...",
  "custom_secret": "sensitive_value"
}
```

**Notes:**
- Returns **actual secret values** (not masked)
- If secrets file doesn't exist, returns empty object `{}`
- Secrets are stored separately from configuration for security

**Security Warning:**
> This endpoint returns raw secrets. Ensure proper access controls are in place.

---

#### Save Secrets

Save secrets to secrets file.

**Request:**
```http
POST /api/v2/secrets
Content-Type: application/json

{
  "ha_token": "eyJ0eXAiOiJKV1QiLC...",
  "solcast_api_key": "abc123xyz...",
  "custom_secret": "sensitive_value"
}
```

**Response:** `200 OK`
```json
{
  "message": "Secrets saved successfully",
  "status": 200
}
```

**Validation:**
- All values must be strings
- Atomic save with file locking
- Empty object `{}` is valid (clears all secrets)

**Error Responses:**

`400 Bad Request` - Invalid secret value type
```json
{
  "error": "Invalid value",
  "details": ["All secret values must be strings"],
  "status": 400
}
```

`400 Bad Request` - No data provided
```json
{
  "error": "Invalid value",
  "details": ["No secrets data provided"],
  "status": 400
}
```

---

### Schema Endpoints

#### Get JSON Schema

Get the JSON Schema for configuration validation.

**Request:**
```http
GET /api/v2/config/schema
```

**Response:** `200 OK`
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "config_version": {
      "type": "integer",
      "const": 2
    },
    "general": {
      "type": "object",
      "properties": { ... }
    },
    ...
  },
  "required": ["config_version", "general", "batteries"]
}
```

**Notes:**
- Schema is generated from Pydantic models
- Use for client-side validation
- Must be generated before starting server (see [Schema Generation](#schema-generation))

**Error Responses:**

`404 Not Found` - Schema not generated
```json
{
  "error": "File not found",
  "details": ["Schema file not found at app/static/schemas/schema.json. Please generate schemas first."],
  "status": 404
}
```

---

#### Get UI Schema

Get the UI Schema for form rendering.

**Request:**
```http
GET /api/v2/config/uischema
```

**Response:** `200 OK`
```json
{
  "type": "Categorization",
  "elements": [
    {
      "type": "Category",
      "label": "General",
      "elements": [ ... ]
    },
    {
      "type": "Category",
      "label": "Batteries",
      "elements": [ ... ]
    }
  ]
}
```

**Notes:**
- UI Schema defines form layout and field types for JSONForms
- Includes custom renderer mappings (e.g., entity picker for HA entities)
- Must be generated before starting server (see [Schema Generation](#schema-generation))

**Error Responses:**

`404 Not Found` - UI Schema not generated
```json
{
  "error": "File not found",
  "details": ["UISchema file not found at app/static/schemas/uischema.json. Please generate schemas first."],
  "status": 404
}
```

---

### Home Assistant Proxy

#### Proxy to Home Assistant API

Proxy requests to Home Assistant API with connection details from headers.

**Request:**
```http
GET /api/v2/ha-proxy/states
X-HA-Host: homeassistant.local
X-HA-Port: 8123
X-HA-Protocol: http
X-HA-Token: eyJ0eXAiOiJKV1QiLC...
```

**Headers:**
- `X-HA-Host` (required) - HA hostname or IP (e.g., "homeassistant.local", "192.168.1.100")
- `X-HA-Port` (optional) - HA port (default: none, HA standard is 8123)
- `X-HA-Protocol` (optional) - Protocol "http" or "https" (default: "http")
- `X-HA-Token` (required) - Long-lived access token from HA

**URL Pattern:**
- Frontend calls: `/api/v2/ha-proxy/{path}`
- Proxied to HA: `{protocol}://{host}:{port}/api/{path}`

**Example:**
```
Request:  GET /api/v2/ha-proxy/states
Proxies:  GET http://homeassistant.local:8123/api/states
```

**Response:**
Returns the exact response from Home Assistant API (status, headers, body).

**Supported Methods:**
All HTTP methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`

**Security Features:**
- Protocol validation (only `http`/`https` allowed)
- SSL certificate verification enabled
- Request timeout (10 seconds)
- Sanitized error messages (no sensitive data reflected)
- `X-Content-Type-Options: nosniff` header added

**Error Responses:**

`400 Bad Request` - Missing required header
```json
{
  "error": "Missing Home Assistant host",
  "details": ["X-HA-Host header is required"],
  "status": 400
}
```

`400 Bad Request` - Invalid protocol
```json
{
  "error": "Invalid protocol",
  "details": ["Protocol must be 'http' or 'https'"],
  "status": 400
}
```

`502 Bad Gateway` - Connection failed
```json
{
  "error": "Cannot connect to Home Assistant",
  "details": ["Connection failed. Check host, port, and network."],
  "status": 502
}
```

`502 Bad Gateway` - SSL error
```json
{
  "error": "SSL certificate verification failed",
  "details": ["SSL/TLS certificate error"],
  "status": 502
}
```

`504 Gateway Timeout` - Request timeout
```json
{
  "error": "Home Assistant request timeout",
  "details": ["Request timed out after 10 seconds"],
  "status": 504
}
```

---

## Usage Examples

### Load Configuration

```bash
curl -X GET http://localhost:5000/api/v2/config
```

### Save Configuration

```bash
curl -X POST http://localhost:5000/api/v2/config \
  -H "Content-Type: application/json" \
  -d '{
    "config_version": 2,
    "general": {
      "time_zone": "Europe/Amsterdam",
      "ha_url": "http://homeassistant.local:8123",
      "ha_token": "!secret ha_token"
    },
    "batteries": []
  }'
```

### Load Secrets

```bash
curl -X GET http://localhost:5000/api/v2/secrets
```

### Save Secrets

```bash
curl -X POST http://localhost:5000/api/v2/secrets \
  -H "Content-Type: application/json" \
  -d '{
    "ha_token": "eyJ0eXAiOiJKV1QiLC...",
    "solcast_api_key": "abc123xyz"
  }'
```

### Get Schema

```bash
curl -X GET http://localhost:5000/api/v2/config/schema
```

### Proxy to Home Assistant

```bash
curl -X GET http://localhost:5000/api/v2/ha-proxy/states \
  -H "X-HA-Host: homeassistant.local" \
  -H "X-HA-Port: 8123" \
  -H "X-HA-Protocol: http" \
  -H "X-HA-Token: eyJ0eXAiOiJKV1QiLC..."
```

---

## Schema Generation

Schemas must be generated before starting the server:

```bash
# From workspace root
source .venv/bin/activate
python dao/frontend/generate_uischema.py

# Output location:
# - dao/webserver/app/static/schemas/schema.json
# - dao/webserver/app/static/schemas/uischema.json
```

Schemas are served via:
- `/api/v2/config/schema` - JSON Schema
- `/api/v2/config/uischema` - UI Schema

**Re-generate schemas after:**
- Updating Pydantic config models
- Adding new configuration fields
- Changing field types or constraints

---

## Security Considerations

### Secrets Handling

1. **Separation**: Secrets stored separately from configuration
2. **!secret References**: Config file contains `!secret key` placeholders
3. **API Returns**: `/api/v2/secrets` returns actual values (not masked)
4. **Logging**: Secret values are **never** logged
5. **File Permissions**: Ensure `secrets.json` has restricted permissions

### File Operations

1. **Atomic Writes**: Configuration and secrets use atomic file operations
2. **File Locking**: Exclusive locks prevent concurrent write corruption
3. **Validation**: All data validated before saving
4. **Backup**: Consider backing up config files before saving

### Home Assistant Proxy

1. **No Credential Storage**: HA credentials sent per-request via headers
2. **Protocol Validation**: Only `http`/`https` allowed (no `javascript:`, `data:`, etc.)
3. **SSL Verification**: Enabled for HTTPS connections
4. **Timeout Protection**: 10-second timeout prevents hanging requests
5. **Sanitized Errors**: Error messages don't reflect user input (XSS protection)
6. **Content-Type Enforcement**: Explicit `Content-Type: application/json` on errors

### General Security

1. **No Authentication**: API assumes addon-level access control
2. **CORS**: Enabled for development, configure for production
3. **Input Validation**: All inputs validated before processing
4. **Error Messages**: Generic error messages (no sensitive data leakage)

---

## Development

### Running Backend

```bash
cd dao/webserver
source ../../.venv/bin/activate
python da_server.py
```

Backend runs on `http://localhost:5000` with debug mode enabled.

### API Testing

Use the examples above with `curl` or use tools like:
- **Postman** - GUI HTTP client
- **HTTPie** - User-friendly CLI: `http GET :5000/api/v2/config`
- **Browser DevTools** - Network tab for frontend debugging

### Logging

API v2 uses Python's `logging` module:

**Log Levels:**
- `ERROR` - Validation failures, connection errors, exceptions
- `INFO` - Successful operations (config loaded, secrets saved, etc.)

**Log Location:**
- Development: Console output
- Production: Home Assistant addon logs

**Never Logged:**
- Secret values
- HA tokens
- Passwords or sensitive data

---

## Changelog

### v2.0.0 (Current)
- Initial API v2 release
- Configuration CRUD operations
- Secrets management
- JSON Schema & UI Schema endpoints
- Home Assistant proxy with header-based configuration
- Comprehensive error handling
- Security hardening (XSS protection, input validation)

---

## Support

For issues or questions:
1. Check this documentation
2. Review [Frontend Developer Guide](frontend/DEVELOPER_GUIDE.md)
3. Check server logs for errors
4. Create GitHub issue with reproduction steps
