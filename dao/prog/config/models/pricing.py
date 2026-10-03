"""
Pricing configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .base import SecretStr
from datetime import date, datetime


class ProductionBonusConfig(BaseModel):
    """Supplier bonus on feed-in during a daily time window (e.g. Zonneplan Zonnebonus)."""

    percentage: dict[str, float] = Field(
        description="Bonus percentage by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "Bonus percentage on the feed-in base price, indexed by effective date. "
            "Before the first date no bonus applies; use 0 to end the bonus. "
            "Format: {'2025-01-01': 10}.",
            "x-unit": "%",
            "x-ui-section": "Production bonus",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, values 0-100",
        },
    )
    window: Literal["sun", "fixed"] = Field(
        default="sun",
        description="Time window in which the bonus applies",
        json_schema_extra={
            "x-help": "'sun': from sunrise to sunset (Zonneplan, Frank Energie). "
            "'fixed': between 'start' and 'end' local time every day (NextEnergy: 06:00-22:00).",
            "x-ui-section": "Production bonus",
        },
    )
    start: str = Field(
        default="06:00",
        description="Start of the fixed window (HH:MM local time)",
        json_schema_extra={
            "x-help": "Only used when window is 'fixed'.",
            "x-ui-section": "Production bonus",
            "x-validation-hint": "Format: HH:MM (24-hour)",
        },
    )
    end: str = Field(
        default="22:00",
        description="End of the fixed window (HH:MM local time)",
        json_schema_extra={
            "x-help": "Only used when window is 'fixed'. Must be later than 'start'.",
            "x-ui-section": "Production bonus",
            "x-validation-hint": "Format: HH:MM (24-hour)",
        },
    )
    sun_location: Literal["home", "nl_center"] = Field(
        default="home",
        alias="sun location",
        description="Location used to calculate sunrise and sunset",
        json_schema_extra={
            "x-help": "'home': the latitude/longitude of your Home Assistant installation. "
            "'nl_center': KNMI De Bilt, as reference for the Netherlands. "
            "Only used when window is 'sun'.",
            "x-ui-section": "Production bonus",
        },
    )
    include_supplier_cost: bool = Field(
        default=True,
        alias="include supplier cost",
        description="Include the supplier production cost in the bonus base",
        json_schema_extra={
            "x-help": "When true the bonus is calculated over (market price + cost supplier production), "
            "as Zonneplan does ((market + 0.02) x 10%). When false only over the market price "
            "(NextEnergy: market x 50%). The bonus is added excluding taxes and VAT.",
            "x-ui-section": "Production bonus",
        },
    )
    only_positive_price: bool = Field(
        default=True,
        alias="only positive price",
        description="Only grant the bonus when the bonus base is positive",
        json_schema_extra={
            "x-help": "When true no bonus is given in intervals where the bonus base price is zero or negative.",
            "x-ui-section": "Production bonus",
        },
    )
    annual_cap: Optional[float] = Field(
        default=None,
        ge=0,
        alias="annual cap",
        description="Maximum feed-in per calendar year that receives the bonus (kWh)",
        json_schema_extra={
            "x-help": "The bonus stops for the rest of the calendar year once this much feed-in "
            "has received the bonus, counted from the 'entities grid production' sensors in the "
            "report settings. Leave empty for no cap. Zonneplan: 7500.",
            "x-unit": "kWh",
            "x-ui-section": "Production bonus",
        },
    )

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("percentage needs at least one date entry")
        for day, percentage in v.items():
            datetime.strptime(day, "%Y-%m-%d")
            if not (0 <= percentage <= 100):
                raise ValueError(
                    f"Bonus percentage must be between 0 and 100, got {percentage} for date {day}"
                )
        return v

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, v: str) -> str:
        datetime.strptime(v, "%H:%M")
        return v

    @field_validator("end")
    @classmethod
    def validate_end_after_start(cls, v: str, info) -> str:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError(f"end ({v}) must be later than start ({start})")
        return v

    model_config = ConfigDict(extra="allow", populate_by_name=True)

class PricePrediction(BaseModel):
    extension: Optional[int] = Field (
        default=0,
        ge=0,
        description="The amount of hours the planninghorizon is extended beyond the horizon of the regular day ahead prices",
        json_schema_extra={
            "x-help": "The amount of hours the planninghorizon is extended beyond the horizon of the regular day ahead prices",
            "x-unit": "h",
            "x-ui-section": "Prices",
        },
    )
    source: Optional[Literal["epexpredictor", "energypriceforecast_eu", "dap"]] = Field (
        default="dap",
        description="The name of the supplier of prediction data, now there is support for epexpredictor, dap and energypriceforecast_eu",
        json_schema_extra={
            "x-help": "The name of the supplier of prediction data, now there is support for epexpredictor, dap and energypriceforecast_eu",
            "x-ui-section": "Prices",
        },
    )
    api: Optional[str] = Field (
        default="https://raw.githubusercontent.com/corneel27/day-ahead-prediction/main/dap/data/prediction.json",
        description="The url of the supplier of prediction data, with which DAO can get the prediction data ",
        json_schema_extra={
            "x-help": "The url of the supplier to get the prediction data"
                      "for Epexpredictor: https://epexpredictor.batzill.com/prices?region=<region>&hours=<hours>"
                      "for energypriceforecast.eu: https://api.energypriceforecast.eu/api/v1/dao/prices?country=<region>&hours=<hours>"
                      "for da_prediction: https://raw.githubusercontent.com/corneel27/day-ahead-prediction/main/dap/data/prediction.json",
            "x-ui-section": "Prices",
        },
    )

class PricingConfig(BaseModel):
    """Day-ahead pricing and tariff configuration."""

    source_day_ahead: Literal["nordpool", "entsoe", "tibber"] = Field(
        default="nordpool",
        alias="source day ahead",
        description="Source for day-ahead prices",
        json_schema_extra={
            "x-help": "Data source for day-ahead electricity market prices. 'nordpool' and 'entsoe' for European markets, 'tibber' if using Tibber integration.",
            "x-ui-section": "Prices",
        },
    )
    prediction: Optional[PricePrediction] = Field(
        default_factory = PricePrediction,
        description="Configuration of getting and using priceprediction beyond the day ahead spotprices of epex.",
        json_schema_extra={
            "x-help": "Configuration of getting and using priceprediction beyond the day ahead spotprices of epex.",
            "x-ui-section": "Prices",
        },
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
                    "schema": {"const": "entsoe"},
                },
            },
        },
    )

    # Date-based tariff configurations (date string -> value)
    energy_taxes_consumption: dict[str, float] = Field(
        alias="energy taxes consumption",
        description="Energy taxes for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on consumption (excluding VAT) indexed by effective date. Format: {'2024-01-01': 0.05}. Use date when tariff changes.",
            "x-unit": "€/kWh",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)",
        },
    )
    energy_taxes_production: dict[str, float] = Field(
        alias="energy taxes production",
        description="Energy taxes for production by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Energy taxes on feed-in/production (excluding VAT) indexed by effective date. Often zero or negative. Format: {'2024-01-01': 0.0}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)",
        },
    )
    cost_supplier_consumption: dict[str, float] = Field(
        alias="cost supplier consumption",
        description="Supplier costs for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)",
        json_schema_extra={
            "x-help": "Supplier markup/fees for consumption (excluding VAT) indexed by effective date. Fixed part of electricity cost. Format: {'2024-01-01': 0.02}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)",
        },
    )
    cost_supplier_production: dict[str, float] = Field(
        alias="cost supplier production",
        description="Supplier costs for production (feed-in) by date (YYYY-MM-DD -> euro/kWh ex VAT) "
                    "negative if you must pay for feed-in, positive if you get income for feed-in ",
        json_schema_extra={
            "x-help": "Supplier fees for feed-in/production (excluding VAT) indexed by effective date. "
                      "Negative if you must pay for feed-in, positive if you get income for feed-in. "
                      "Format: {'2024-01-01': -0.02}.",
            "x-unit": "€/kWh",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float values (ex VAT)",
        },
    )
    vat_consumption: dict[str, float] = Field(
        alias="vat consumption",
        description="VAT percentage for consumption by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on consumption indexed by effective date. Format: {'2024-01-01': 21}. Applied to market price + taxes + supplier costs.",
            "x-unit": "%",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values",
        },
    )
    vat_production: dict[str, float] = Field(
        alias="vat production",
        description="VAT percentage for production by date (YYYY-MM-DD -> %)",
        json_schema_extra={
            "x-help": "VAT percentage on feed-in/production indexed by effective date. Format: {'2024-01-01': 21}. Often same as consumption VAT.",
            "x-unit": "%",
            "x-ui-section": "Taxes",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, integer 0-100 values",
        },
    )
    multiplier_consumption: Optional[dict[str, float]] = Field(
        default={"2000-01-01": 1.0},
        alias="multiplier consumption",
        description="Multiplier for consumption by date (YYYY-MM-DD -> x.xx)",
        json_schema_extra={
            "x-help": "Multiplier on consumption day-ahead price indexed by effective date. Format: {'2024-01-01': 0.94}.",
            "x-unit": "-",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float -100.0 - +100.0 values",
        },
    )
    multiplier_production: Optional[dict[str, float]] = Field(
        default={"2000-01-01": 1.0},
        alias="multiplier production",
        description="Multiplier for production by date (YYYY-MM-DD -> x.xx)",
        json_schema_extra={
            "x-help": "Multiplier on feed-in/production day-ahead price indexed by effective date. Format: {'2024-01-01': 0.94}.",
            "x-unit": "-",
            "x-ui-section": "Cost",
            "x-validation-hint": "Dict with YYYY-MM-DD keys, float -100.0 - +100.0 values",
        },
    )
    # Invoice settings
    last_invoice: date = Field(
        alias="last invoice",
        description="Date of last invoice (YYYY-MM-DD)",
        json_schema_extra={
            "x-help": "Date of last electricity invoice. Used for calculating costs since last billing period. Format: YYYY-MM-DD. Update after receiving invoices.",
            "x-ui-section": "Prices",
            "x-validation-hint": "Must be YYYY-MM-DD format",
        },
    )
    tax_refund: bool = Field(
        default=True,
        alias="tax refund",
        description="Whether tax refund applies",
        json_schema_extra={
            "x-help": "Enable tax refund calculation if eligible. Some regions/users get energy tax refunds for solar production.",
            "x-ui-section": "Taxes",
        },
    )
    production_bonus: Optional[ProductionBonusConfig] = Field(
        default=None,
        alias="production bonus",
        description="Supplier bonus on feed-in during a daily time window",
        json_schema_extra={
            "x-help": "Bonus some suppliers pay on feed-in during part of the day, "
            "e.g. the Zonneplan Zonnebonus: 10% over (market price + 0.02) from sunrise to sunset, "
            "only when that sum is positive, up to 7500 kWh per year. "
            "The bonus is added to the production price per interval, so the optimizer "
            "and the reports take it into account. Leave empty when not applicable.",
            "x-ui-section": "Production bonus",
        },
    )

    @field_validator("vat_consumption", "vat_production")
    @classmethod
    def validate_vat_percentages(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate VAT percentages are between 0 and 100."""
        for date, percentage in v.items():
            if not (0 <= percentage <= 100):
                raise ValueError(
                    f"VAT percentage must be between 0 and 100, got {percentage} for date {date}"
                )
        return v

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        json_schema_extra={
            "x-ui-group": "Pricing",
            "x-icon": "currency-eur",
            "x-order": 11,
            "x-help": """# Pricing & Tariff Configuration

Configure electricity market prices and tariff components for accurate cost optimization.

## Price Components

Total electricity cost consists of:
1. **Market price**: Day-ahead spot price (nordpool/entsoe/tibber)
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

## Production Bonus

Some suppliers pay a bonus on feed-in during part of the day. Per interval:

bonus = percentage × (market + supplier production cost), added to the production price
(excluding taxes and VAT), only inside the window and when the base is positive.

Zonneplan Zonnebonus (10% from sunrise to sunset, max 7500 kWh per year):
```json
"production bonus": {
  "percentage": {"2025-01-01": 10},
  "window": "sun",
  "annual cap": 7500
}
```

NextEnergy (50% over the market price, 06:00-22:00):
```json
"production bonus": {
  "percentage": {"2025-01-01": 50},
  "window": "fixed", "start": "06:00", "end": "22:00",
  "include supplier cost": false
}
```

Intervals that are only partly inside the window get a proportional share of the bonus.
The annual cap is counted from the recorded grid feed-in: the `entities grid production`
sensors in the report settings, or else the `prod` values in the DAO database.
Only feed-in inside the window with a positive bonus base counts; hourly values are
spread evenly over their quarters before that check.

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
""",
            "x-docs-url": "https://github.com/corneel27/day-ahead/wiki/Pricing-Configuration",
        },
    )
