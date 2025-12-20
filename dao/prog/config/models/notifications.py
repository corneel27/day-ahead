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
        description="HA entity for notifications",
        json_schema_extra={
            "x-help": "Optional: Home Assistant notification service entity. Used to send notifications about optimization events. Example: 'notify.mobile_app' or 'notify.persistent_notification'.",
            "x-category": "basic",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "notify"
        }
    )
    opstarten: bool | str = Field(
        default="false",
        description="Send notification on startup",
        json_schema_extra={
            "x-help": "Send notification when Day Ahead Optimizer starts up. Useful for monitoring add-on status. Can be boolean or HA entity ID.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    berekening: bool | str = Field(
        default="false",
        description="Send notification on calculation completion",
        json_schema_extra={
            "x-help": "Send notification when optimization calculation completes. Includes summary of results (costs, battery schedule, etc.). Can be boolean or HA entity ID.",
            "x-category": "basic",
            "x-ui-widget": "entity-picker-or-boolean"
        }
    )
    last_activity_entity: Optional[str] = Field(
        default=None,
        alias="last activity entity",
        description="HA entity to track last activity timestamp",
        json_schema_extra={
            "x-help": "Optional: Home Assistant entity to update with last activity timestamp. Useful for monitoring and automations. Example: 'input_datetime.dao_last_run'.",
            "x-category": "advanced",
            "x-ui-widget": "entity-picker",
            "x-entity-filter": "input_datetime,datetime,sensor"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Integration',
            'x-icon': 'bell',
            'x-order': 14,
            'x-help': '''# Notifications Configuration

Configure Home Assistant notifications for optimization events.

## Notification Types

### Startup Notifications (opstarten)
- Sent when add-on starts/restarts
- Useful for monitoring system health
- Helps diagnose startup issues

### Calculation Notifications (berekening)
- Sent after each optimization run
- Includes optimization summary:
  - Total costs (consumption/production)
  - Battery charge schedule
  - Device scheduling results
  - Warnings or errors

## Setup

1. Configure notification service in HA
2. Set notification_entity to your service
3. Enable desired notification types
4. Optional: Track activity with timestamp entity

## Tips

- Use mobile app notifications for important alerts
- Use persistent notifications for detailed results
- Disable during testing to avoid notification spam
- Consider automations based on last_activity_entity
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Notifications-Configuration',
            'x-category': 'integration',
            'x-collapsible': True
        }
    )
