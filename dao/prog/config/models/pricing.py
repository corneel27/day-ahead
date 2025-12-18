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
        alias="source day ahead",
        description="Source for day-ahead prices"
    )
    entsoe_api_key: Optional[str | SecretStr] = Field(
        default=None,
        alias="entsoe-api-key",
        description="ENTSO-E API key (can use !secret)"
    )
    regular_high: float = Field(
        alias="regular high",
        ge=0,
        description="Regular high tariff fallback (euro/kWh)"
    )
    regular_low: float = Field(
        alias="regular low",
        ge=0,
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
        populate_by_name=True
    )
