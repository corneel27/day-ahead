"""
Pricing configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from .base import SecretStr


class PricingConfig(BaseModel):
    """Day-ahead pricing and tariff configuration."""
    
    source_day_ahead: str = Field(
        alias="source day ahead",
        description="Source for day-ahead prices: 'nordpool' | 'entsoe' | 'tibber'"
    )
    entsoe_api_key: Optional[str | SecretStr] = Field(
        default=None,
        alias="entsoe-api-key",
        description="ENTSO-E API key (can use !secret)"
    )
    regular_high: float = Field(
        alias="regular high",
        description="Regular high tariff fallback (euro/kWh)"
    )
    regular_low: float = Field(
        alias="regular low",
        description="Regular low tariff fallback (euro/kWh)"
    )
    switch_to_low: int = Field(
        alias="switch to low",
        ge=0, le=23,
        description="Hour to switch to low tariff"
    )
    
    # Date-based tariff configurations (date string -> value)
    energy_taxes_consumption: dict[str, float] = Field(
        alias="energy taxes consumption",
        description="Energy taxes for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)"
    )
    energy_taxes_production: dict[str, float] = Field(
        alias="energy taxes production",
        description="Energy taxes for production by date (YYYY-MM-DD -> euro/kWh ex VAT)"
    )
    cost_supplier_consumption: dict[str, float] = Field(
        alias="cost supplier consumption",
        description="Supplier costs for consumption by date (YYYY-MM-DD -> euro/kWh ex VAT)"
    )
    cost_supplier_production: dict[str, float] = Field(
        alias="cost supplier production",
        description="Supplier costs for production by date (YYYY-MM-DD -> euro/kWh ex VAT)"
    )
    vat_consumption: dict[str, int] = Field(
        alias="vat consumption",
        description="VAT percentage for consumption by date (YYYY-MM-DD -> %)"
    )
    vat_production: dict[str, int] = Field(
        alias="vat production",
        description="VAT percentage for production by date (YYYY-MM-DD -> %)"
    )
    
    # Invoice settings
    last_invoice: str = Field(
        alias="last invoice",
        description="Date of last invoice (YYYY-MM-DD)"
    )
    tax_refund: bool | str = Field(
        alias="tax refund",
        description="Whether tax refund applies"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
