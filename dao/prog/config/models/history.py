"""
History/data retention configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class HistoryConfig(BaseModel):
    """History and data retention settings."""
    
    save_days: int = Field(
        alias="save days",
        default=7,
        ge=1,
        description="Number of days to retain historical data"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
