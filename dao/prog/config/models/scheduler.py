"""
Scheduler configuration models.
"""

from pydantic import BaseModel, Field, ConfigDict


class SchedulerConfig(BaseModel):
    """
    Task scheduler configuration.
    
    Maps time patterns to action names.
    Time patterns can be:
    - Specific times: "0435", "1255"
    - Wildcards: "xx00" (every hour at :00), "xx15" (every hour at :15)
    
    Actions include:
    - get_meteo_data
    - get_tibber_data
    - get_day_ahead_prices
    - calc_optimum
    - clean_data
    - calc_baseloads
    """
    
    # This is a flexible dict - keys are time patterns, values are action names
    # Using root_model would be more correct but this works for now
    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={
            'x-ui-group': 'Automation',
            'x-icon': 'clock-outline',
            'x-order': 18,
            'x-help': '''# Scheduler Configuration

Define when automatic tasks run using time patterns.

## Time Pattern Format

- **Specific time**: "0435" (4:35 AM), "1255" (12:55 PM)
- **Hourly wildcard**: "xx00" (every hour at :00), "xx15" (every hour at :15)
- **Format**: HHMM (24-hour, no colons)

## Available Actions

### Data Collection
- **get_meteo_data**: Fetch weather forecasts (solar irradiation, temperature)
- **get_tibber_data**: Fetch Tibber prices (if using Tibber)
- **get_day_ahead_prices**: Fetch day-ahead market prices

### Optimization
- **calc_optimum**: Run main optimization algorithm
- **calc_baseloads**: Calculate baseline consumption from history

### Maintenance
- **clean_data**: Clean up old data (runs save_days retention)

## Example Configuration

```json
{
  "0435": "get_day_ahead_prices",
  "0445": "get_meteo_data",
  "0500": "calc_optimum",
  "xx00": "calc_baseloads",
  "0300": "clean_data"
}
```

## Typical Schedule

1. **04:00-05:00**: Fetch prices and weather (after day-ahead auction)
2. **05:00**: Run optimization with fresh data
3. **Hourly**: Update baseload calculations
4. **03:00**: Clean old data (low activity time)

## Tips

- Day-ahead prices available after ~13:00 (CET) for next day
- Run optimization after all data fetched
- Hourly baseload updates improve accuracy
- Clean data during low activity (night)
- Avoid overlapping long-running tasks
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Scheduler-Configuration',
            'x-category': 'automation',
            'x-collapsible': True
        }
    )
    
    def __init__(self, **data):
        """Accept arbitrary time->action mappings."""
        super().__init__()
        # Store all data as attributes for dict-like access
        for key, value in data.items():
            object.__setattr__(self, key, value)
    
    def items(self):
        """Allow dict-like iteration."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}.items()
    
    def get(self, key, default=None):
        """Allow dict-like access."""
        return getattr(self, key, default)
