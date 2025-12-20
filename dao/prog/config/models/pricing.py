"""
Pricing configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .base import SecretStr
from datetime import datetime


class PricingConfig(BaseModel):
    """Day-ahead pricing and tariff configuration."""
    
    source_day_ahead: Literal['nordpool', 'entsoe', 'tibber'] = Field(
        default='nordpool',
        alias="source day ahead",
        description="Source for day-ahead prices",
        json_schema_extra={
            "x-help": "Data source for day-ahead electricity market prices. 'nordpool' for Nordic/Baltic, 'entsoe' for European markets, 'tibber' if using Tibber integration.",
            "x-category": "basic"
        }
    )
    entsoe_api_key: Optional[str | SecretStr] = Field(
        default=None,
        alias="entsoe-api-key",
        description="ENTSO-E API key (can use !secret)",
        json_schema_extra={
            "x-help": "API key for ENTSO-E Transparency Platform. Required if source_day_ahead='entsoe'. Get free key at transparency.entsoe.eu. Use !secret for security.",
            "x-category": "basic",
            "x-validation-hint": "Required for entsoe source, use !secret",
            "x-docs-url": "https://transparency.entsoe.eu/"
        }
    )
    
    # Date-based tariff configurations (date string -> value)
    energy_taxes_consumption: dict[str, float] = Field(
        alias="energy taxes consumption",
        description="Energy taxes for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on consumption (excluding VAT) indexed by effective date. Format: {'2024-01-01': 0.05}. Use date when tariff changes.",
            "x-unit": "€/kWh",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    energy_taxes_production: dict[str, float] = Field(
        alias="energy taxes production",
        description="Energy taxes for production by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on feed-in/production (excluding VAT) indexed by effective date. Often zero or negative. Format: {'2024-01-01': 0.0}.",
            "x-unit": "€/kWh",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    cost_supplier_consumption: dict[str, float] = Field(
        alias="cost supplier consumption",
        description="Supplier costs for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Supplier markup/fees for consumption (excluding VAT) indexed by effective date. Fixed part of electricity cost. Format: {'2024-01-01': 0.02}.",
            "x-unit": "€/kWh",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    cost_supplier_production: dict[str, float] = Field(
        alias="cost supplier production",
        description="Supplier costs for production by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Supplier fees for feed-in/production (excluding VAT) indexed by effective date. May be negative (credit). Format: {'2024-01-01': -0.02}.",
            "x-unit": "€/kWh",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    vat_consumption: dict[str, int] = Field(
        alias="vat consumption",
        description="VAT percentage for consumption by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on consumption indexed by effective date. Format: {'2024-01-01': 21}. Applied to market price + taxes + supplier costs.",
            "x-unit": "%",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values"
        }
    )
    vat_production: dict[str, int] = Field(
        alias="vat production",
        description="VAT percentage for production by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on feed-in/production indexed by effective date. Format: {'2024-01-01': 21}. Often same as consumption VAT.",
            "x-unit": "%",
            "x-category": "basic",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values"
        }
    )
    
    # Invoice settings
    last_invoice: str = Field(
        alias="last invoice",
        description="Date of last invoice (YYYY-MM-DD)",
        json_schema_extra={
            "x-help": "Date of last electricity invoice. Used for calculating costs since last billing period. Format: YYYY-MM-DD. Update after receiving invoices.",
            "x-category": "basic",
            "x-validation-hint": "Must be YYYY-MM-DD format"
        }
    )
    tax_refund: bool | str = Field(
        alias="tax refund",
        description="Whether tax refund applies",
        json_schema_extra={
            "x-help": "Enable tax refund calculation if eligible. Some regions/users get energy tax refunds for solar production. Can be boolean or HA entity ID.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    
    @field_validator('vat_consumption', 'vat_production')
    @classmethod
    def validate_vat_percentages(cls, v: dict[str, int]) -> dict[str, int]:
        """Validate VAT percentages are between 0 and 100."""
        for date, percentage in v.items():
            if not (0 <= percentage <= 100):
                raise ValueError(f"VAT percentage must be between 0 and 100, got {percentage} for date {date}")
        return v
    
    @field_validator('last_invoice')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got: {v}")
        return v
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Pricing & Markets',
            'x-icon': 'currency-eur',
            'x-order': 11,
            'x-help': '''# Pricing & Tariff Configuration

Configure electricity market prices and tariff components for accurate cost optimization.

## Price Components

Total electricity cost consists of:
1. **Market price**: Day-ahead spot price (nordpool/entsoe/tibber)
2. **Energy taxes**: Government energy taxes
3. **Supplier costs**: Your supplier's markup/fees
4. **VAT**: Value-added tax on sum of above

Consumption price = (market + taxes + supplier) × (1 + VAT)

## Date-Based Tariffs

All tariff fields use date-indexed dictionaries:
```json
{
  "2024-01-01": 0.05,
  "2024-07-01": 0.06
}
```

System uses tariff active on optimization date.

## Data Sources

- **nordpool**: Nord Pool (Nordic/Baltic markets)
- **entsoe**: ENTSO-E Transparency Platform (all European markets)
- **tibber**: Tibber API (if using Tibber as supplier)

## Tips

- All prices are EXCLUDING VAT (VAT applied separately)
- Update tariffs when your supplier changes prices
- Use !secret for API keys
- Production costs often lower than consumption (or negative for feed-in credit)
- Keep last_invoice updated for accurate cost tracking
- Check your electricity bill for exact tariff components
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Pricing-Configuration',
            'x-category': 'infrastructure',
            'x-collapsible': True
        }
    )
