"""
Home Assistant connection configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from .base import SecretStr


class HomeAssistantConfig(BaseModel):
    """Home Assistant connection configuration."""
    
    ip_address: Optional[str] = Field(
        default=None,
        alias="host",
        description="Home Assistant IP address (auto-detected if not set)",
        json_schema_extra={
            "x-help": "Home Assistant IP address or hostname. Usually auto-detected when running as HA add-on. Set manually only if auto-detection fails. Examples: '192.168.1.100', 'homeassistant.local'.",
            "x-category": "advanced"
        }
    )
    ip_port: Optional[int] = Field(
        default=None,
        alias="ip port",
        description="Home Assistant port (default: 8123)",
        json_schema_extra={
            "x-help": "Home Assistant web interface port. Default is 8123. Change only if using custom port. Usually auto-detected when running as add-on.",
            "x-unit": "port",
            "x-category": "advanced",
            "x-validation-hint": "Default 8123, change if custom"
        }
    )
    hasstoken: Optional[str | SecretStr] = Field(
        default=None,
        description="Home Assistant long-lived access token (can use !secret)",
        alias="token",
        json_schema_extra={
            "x-help": "Long-lived access token for HA API. Usually auto-provided when running as add-on. Create manually: Profile → Security → Long-Lived Access Tokens. Use !secret for security.",
            "x-category": "advanced",
            "x-validation-hint": "Auto-provided as add-on, use !secret if manual"
        }
    )
    protocol_api: Optional[Literal['http', 'https']] = Field(
        default=None,
        alias="protocol api",
        description="API protocol",
        json_schema_extra={
            "x-help": "Protocol for Home Assistant API. 'http' for local access, 'https' for SSL/TLS. Usually auto-detected. Set manually only if needed.",
            "x-category": "expert"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Integration',
            'x-icon': 'home-assistant',
            'x-order': 20,
            'x-help': '''# Home Assistant Connection

Configure connection to Home Assistant for API access.

## Auto-Detection (Recommended)

When running as Home Assistant add-on:
- ✅ IP address auto-detected
- ✅ Port auto-detected
- ✅ Access token auto-provided
- ✅ Protocol auto-detected

**Leave all fields empty for automatic configuration.**

## Manual Configuration

Only needed if:
- Running outside Home Assistant
- Auto-detection fails
- Using custom HA setup

### Long-Lived Access Token

1. In Home Assistant: Profile → Security
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Name it "Day Ahead Optimizer"
5. Copy token immediately (shown once!)
6. Store in secrets.json:
   ```json
   {"ha_token": "your_token_here"}
   ```
7. Reference in config:
   ```json
   "token": "!secret ha_token"
   ```

## Troubleshooting

- **Connection refused**: Check IP/port
- **Unauthorized**: Token invalid or expired
- **SSL errors**: Check protocol setting
- **Timeout**: Network connectivity issues

## Tips

- Prefer auto-detection when possible
- Always use !secret for tokens
- Test connection from dashboard
- Check HA logs if issues persist
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Home-Assistant-Connection',
            'x-category': 'integration',
            'x-collapsible': True
        }
    )
