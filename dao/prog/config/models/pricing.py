"""
Pricing configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .base import SecretStr
from datetime import date


class PricingConfig(BaseModel):
    """Day-ahead pricing and tariff configuration."""

    source_day_ahead: Literal['nordpool', 'entsoe', 'easyenergy', 'tibber'] = Field(
        default='nordpool',
        alias="source day ahead",
        description="Source for day-ahead prices",
        json_schema_extra={
            "x-help": "Data source for imported official day-ahead electricity market prices. 'nordpool' for Nordic/Baltic, 'entsoe' for European markets, 'easyenergy' for the EasyEnergy public tariff feed, 'tibber' if using Tibber integration.",
            "x-ui-section": "Prices"
        }
    )
    entsoe_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="entsoe-api-key",
        description="ENTSO-E API key (can use !secret)",
        json_schema_extra={
            "x-help": "API key for ENTSO-E Transparency Platform. Required if source_day_ahead='entsoe'. Get free key at transparency.entsoe.eu. Use !secret for security.",
            "x-ui-section": "Prices",
            "x-validation-hint": "Required for entsoe source, use !secret",
            "x-docs-url": "https://transparency.entsoe.eu/",
            "x-ui-rules": {
                "effect": "SHOW",
                "condition": {
                    "scope": "#/properties/source_day_ahead",
                    "schema": {
                        "const": "entsoe"
                    }
                }
            }
        }
    )
    forecast_extension_provider: Literal['none', 'energypriceforecast', 'dayaheadprediction'] = Field(
        default='none',
        alias="forecast extension provider",
        description="Optional provider for extending the day-ahead horizon with forecast data",
        json_schema_extra={
            "x-help": "Optional provider that extends the imported official day-ahead horizon with forecast prices. The extension never replaces already imported official prices.",
            "x-ui-section": "Prices",
        }
    )
    forecast_extension_hours: int = Field(
        default=0,
        alias="forecast extension hours",
        description="How many additional hours should be appended beyond the official day-ahead horizon",
        json_schema_extra={
            "x-help": "Number of hours to extend beyond the imported official day-ahead horizon. DAO translates this into the provider-specific URL parameter.",
            "x-ui-section": "Prices",
            "x-validation-hint": "Integer between 0 and 168"
        }
    )
    energypriceforecast_extension_api_url: Optional[str] = Field(
        default="https://api.energypriceforecast.eu/api/v1/dao/prices",
        alias="energypriceforecast-extension-api-url",
        description="Energy Price Forecast EU extension API URL",
        json_schema_extra={
            "x-help": "Provider-specific URL for the Energy Price Forecast EU horizon extension feed. Expected response: format=dao-prices with entries[].",
            "x-ui-section": "Prices",
            "x-ui-rules": {
                "effect": "SHOW",
                "condition": {
                    "scope": "#/properties/forecast_extension_provider",
                    "schema": {
                        "const": "energypriceforecast"
                    }
                }
            }
        }
    )
    energypriceforecast_extension_country: Optional[str] = Field(
        default=None,
        alias="energypriceforecast-extension-country",
        description="Override country code for Energy Price Forecast EU extension",
        json_schema_extra={
            "x-help": "Optional explicit country/market code for the Energy Price Forecast EU extension feed, for example 'nl', 'de', 'dk1' or 'no3'. Leave empty to map from DAO country automatically.",
            "x-ui-section": "Prices",
            "x-ui-rules": {
                "effect": "SHOW",
                "condition": {
                    "scope": "#/properties/forecast_extension_provider",
                    "schema": {
                        "const": "energypriceforecast"
                    }
                }
            }
        }
    )
    day_ahead_prediction_extension_url: Optional[str] = Field(
        default="https://raw.githubusercontent.com/corneel27/day-ahead-prediction/main/dap/data/prediction.json",
        alias="day-ahead-prediction-extension-url",
        description="day-ahead-prediction extension URL",
        json_schema_extra={
            "x-help": "Provider-specific URL for the corneel27/day-ahead-prediction extension feed. Expected response: JSON array with fields like time_ts and prediction. This provider currently only fits the NL market.",
            "x-ui-section": "Prices",
            "x-ui-rules": {
                "effect": "SHOW",
                "condition": {
                    "scope": "#/properties/forecast_extension_provider",
                    "schema": {
                        "const": "dayaheadprediction"
                    }
                }
            }
        }
    )
    
    # Date-based tariff configurations (date string -> value)
    energy_taxes_consumption: dict[str, float] = Field(
        alias="energy taxes consumption",
        description="Energy taxes for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on consumption (excluding VAT) indexed by effective date. Format: {'2024-01-01': 0.05}. Use date when tariff changes.",
            "x-unit": "€/kWh",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    energy_taxes_production: dict[str, float] = Field(
        alias="energy taxes production",
        description="Energy taxes for production by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on feed-in/production (excluding VAT) indexed by effective date. Often zero or negative. Format: {'2024-01-01': 0.0}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    cost_supplier_consumption: dict[str, float] = Field(
        alias="cost supplier consumption",
        description="Supplier costs for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Supplier markup/fees for consumption (excluding VAT) indexed by effective date. Fixed part of electricity cost. Format: {'2024-01-01': 0.02}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    cost_supplier_production: dict[str, float] = Field(
        alias="cost supplier production",
        description="Supplier costs for production by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Supplier fees for feed-in/production (excluding VAT) indexed by effective date. May be negative (credit). Format: {'2024-01-01': -0.02}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)"
        }
    )
    vat_consumption: dict[str, float] = Field(
        alias="vat consumption",
        description="VAT percentage for consumption by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on consumption indexed by effective date. Format: {'2024-01-01': 21}. Applied to market price + taxes + supplier costs.",
            "x-unit": "%",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values"
        }
    )
    vat_production: dict[str, float] = Field(
        alias="vat production",
        description="VAT percentage for production by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on feed-in/production indexed by effective date. Format: {'2024-01-01': 21}. Often same as consumption VAT.",
            "x-unit": "%",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values"
        }
    )
    multiplier_consumption: Optional[dict[str, float]] = Field(
        default={"2000-01-01": 1.0},
        alias="multiplier consumption",
        description="Multiplier for consumption by date (YYYY-MM-DD -> x.xx)",
        json_schema_extra={
            "x-help": "Multiplier on consumption day-ahead price indexed by effective date. Format: {'2024-01-01': 0.94}.",
            "x-unit": "-",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float -100.0 - +100.0 values"
        }
    )
    multiplier_production: Optional[dict[str, float]] = Field(
        default={"2000-01-01": 1.0},
        alias="multiplier production",
        description="Multiplier for production by date (YYYY-MM-DD -> x.xx)",
        json_schema_extra={
            "x-help": "Multiplier on feed-in/production day-ahead price indexed by effective date. Format: {'2024-01-01': 0.94}.",
            "x-unit": "-",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float -100.0 - +100.0 values"
        }
    )
    # Invoice settings
    last_invoice: date = Field(
        alias="last invoice",
        description="Date of last invoice (YYYY-MM-DD)",
        json_schema_extra={
            "x-help": "Date of last electricity invoice. Used for calculating costs since last billing period. Format: YYYY-MM-DD. Update after receiving invoices.",
            "x-ui-section": "Prices",
            "x-validation-hint": "Must be YYYY-MM-DD format"
        }
    )
    tax_refund: bool = Field(
        default=True,
        alias="tax refund",
        description="Whether tax refund applies",
        json_schema_extra={
            "x-help": "Enable tax refund calculation if eligible. Some regions/users get energy tax refunds for solar production.",
            "x-ui-section": "Taxes"
        }
    )
    
    @field_validator('vat_consumption', 'vat_production')
    @classmethod
    def validate_vat_percentages(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate VAT percentages are between 0 and 100."""
        for date, percentage in v.items():
            if not (0 <= percentage <= 100):
                raise ValueError(f"VAT percentage must be between 0 and 100, got {percentage} for date {date}")
        return v

    @field_validator('forecast_extension_hours')
    @classmethod
    def validate_forecast_extension_hours(cls, v: int) -> int:
        if not (0 <= v <= 168):
            raise ValueError("forecast extension hours must be between 0 and 168")
        return v
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Pricing',
            'x-icon': 'currency-eur',
            'x-order': 11,
            'x-help': '''# Pricing & Tariff Configuration

Configure electricity market prices and tariff components for accurate cost optimization.

## Price Components

Total electricity cost consists of:
1. **Market price**: Imported official day-ahead spot price (nordpool/entsoe/easyenergy/tibber)
2. **Energy taxes**: Government energy taxes
3. **Supplier costs**: Your supplier's markup/fees
4. **VAT**: Value-added tax on sum of above
5. **Multiplier**: For calculation of productionprice in Belgium 

Price = (market*multiplier + taxes + supplier) × (1 + VAT)

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
- **easyenergy**: EasyEnergy tariff endpoint
- **tibber**: Tibber API (if using Tibber as supplier)

## Optional Horizon Extension

- **forecast extension provider**: Optional forecast provider for extending the imported official horizon
- **forecast extension hours**: How many additional hours should be appended beyond the official horizon
- **energypriceforecast**: Provider-specific extension feed from Energy Price Forecast EU

## Tips

- All prices are EXCLUDING VAT (VAT applied separately)
- Update tariffs when your supplier changes prices
- Use !secret for API keys
- Production costs often lower than consumption (or negative for feed-in credit)
- Keep last_invoice updated for accurate cost tracking
- Check your electricity bill for exact tariff components
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Pricing-Configuration'
        }
    )
