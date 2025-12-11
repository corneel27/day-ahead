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
        extra='allow'
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
