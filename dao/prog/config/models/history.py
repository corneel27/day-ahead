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
        description="Number of days to retain historical data",
        json_schema_extra={
            "x-help": "Number of days to retain optimization history in database. Older data is automatically cleaned up. Longer retention enables better trend analysis but increases database size. Minimum 1 day.",
            "x-unit": "days",
            "x-category": "basic",
            "x-validation-hint": "Must be >= 1, typical 7-30 days"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Infrastructure',
            'x-icon': 'database-clock',
            'x-order': 15,
            'x-help': '''# History & Data Retention

Control how long optimization history is retained in the database.

## What Gets Stored

- Optimization results (costs, schedules)
- Price data (day-ahead, tariffs)
- Device schedules (battery, EV, heating)
- Solar production forecasts
- Baseload consumption data

## Retention Guidelines

- **7 days**: Minimal retention, recent data only
- **14 days**: Two weeks for comparison
- **30 days**: Monthly trends and analysis
- **90+ days**: Long-term analysis (larger database)

## Database Growth

- More retention = larger database
- Typical: ~1-5 MB per day (depends on devices)
- Monitor database size if using SQLite
- Consider periodic backups

## Tips

- Start with 7-14 days, increase if needed
- Check database size regularly
- Old data cleaned up automatically
- Increase for detailed cost analysis
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/History-Configuration',
            'x-category': 'infrastructure',
            'x-collapsible': True
        }
    )
