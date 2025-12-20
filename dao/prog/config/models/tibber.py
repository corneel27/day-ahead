"""
Tibber integration configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from .base import SecretStr


class TibberConfig(BaseModel):
    """Tibber API integration configuration."""
    
    api_token: str | SecretStr = Field(
        alias="api_token",
        description="Tibber API token (can use !secret)",
        json_schema_extra={
            "x-help": "Tibber API access token. Get from Tibber app or developer portal. Use !secret for security. Required if using Tibber as price source.",
            "x-ui-section": "General",
            "x-validation-hint": "Use !secret for API tokens",
            "x-docs-url": "https://developer.tibber.com/"
        }
    )
    api_url: Optional[str] = Field(
        default="https://api.tibber.com/v1-beta/gql",
        alias="api url",
        description="Tibber API URL",
        json_schema_extra={
            "x-help": "Tibber GraphQL API endpoint URL. Default is official API. Change only for testing or custom endpoints.",
            "x-ui-section": "General"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Integration',
            'x-icon': 'lightning-bolt',
            'x-order': 19,
            'x-help': '''# Tibber Integration

Connect to Tibber API for real-time prices and consumption data.

## What is Tibber?

Tibber is an electricity supplier offering:
- Real-time spot price electricity
- Hour-by-hour pricing
- Smart home integrations
- Carbon-aware pricing

## Setup

1. Sign up for Tibber account
2. Get API token from Tibber app:
   - Settings → Developer → Personal Token
3. Store in secrets.json:
   ```json
   {"tibber_token": "your_token_here"}
   ```
4. Reference in config:
   ```json
   "api_token": "!secret tibber_token"
   ```

## When to Use

- **Yes**: If Tibber is your electricity supplier
- **Yes**: Want real-time Tibber prices in optimization
- **No**: If using other price sources (nordpool, entsoe)

## API Usage

- Fetches hourly prices
- Retrieves consumption history
- Updates price forecasts
- Rate-limited (stay within API limits)

## Tips

- Always use !secret for API token
- Set pricing source to 'tibber' if using
- Tibber provides next-day prices after ~13:00 CET
- Combine with Tibber HA integration for full experience
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Tibber-Integration'
        }
    )
