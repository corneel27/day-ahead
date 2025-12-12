"""
Notification configuration models.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class NotificationsConfig(BaseModel):
    """Notification settings for Home Assistant."""
    
    notification_entity: Optional[str] = Field(
        default=None,
        alias="notification entity",
        description="HA entity for notifications"
    )
    opstarten: bool | str = Field(
        default="false",
        description="Send notification on startup"
    )
    berekening: bool | str = Field(
        default="false",
        description="Send notification on calculation completion"
    )
    last_activity_entity: Optional[str] = Field(
        default=None,
        alias="last activity entity",
        description="HA entity to track last activity timestamp"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
