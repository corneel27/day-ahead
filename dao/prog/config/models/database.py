"""
Database configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict
from .base import SecretStr


class HADatabaseConfig(BaseModel):
    """Home Assistant database connection configuration."""
    
    engine: Literal["mysql", "sqlite", "postgresql"] = Field(
        default="mysql",
        description="Database engine type"
    )
    server: Optional[str] = Field(
        default=None,
        description="Database server hostname (required for mysql/postgresql)"
    )
    port: Optional[int] = Field(
        default=None,
        ge=1, le=65535,
        description="Database port (defaults: mysql=3306, postgresql=5432)"
    )
    database: str = Field(
        default="homeassistant",
        description="Database name"
    )
    username: str = Field(
        default="homeassistant",
        description="Database username"
    )
    password: Optional[str | SecretStr] = Field(
        default=None,
        description="Database password (can use !secret)"
    )
    
    model_config = ConfigDict(
        extra='allow',  # Preserve unknown keys
        populate_by_name=True
    )
    
    @model_validator(mode='after')
    def validate_engine_requirements(self) -> 'HADatabaseConfig':
        """Validate engine-specific requirements and set defaults."""
        if self.engine in ('mysql', 'postgresql'):
            # Validate server is provided
            if not self.server:
                raise ValueError(f"'server' is required when engine is '{self.engine}'")
            
            # Set default port if not provided
            if self.port is None:
                self.port = 3306 if self.engine == 'mysql' else 5432
        
        return self


class DatabaseConfig(BaseModel):
    """
    Day Ahead database configuration (database da).
    
    Can be either SQLite, MySQL/MariaDB, or PostgreSQL.
    """
    
    engine: Literal['sqlite', 'mysql', 'postgresql'] = Field(
        default="sqlite",
        description="Database engine type"
    )
    
    # SQLite fields
    db_path: Optional[str] = Field(
        default=None,
        description="Database path for SQLite (e.g., '../data')"
    )
    database: Optional[str] = Field(
        default=None,
        description="Database filename for SQLite or database name for MySQL"
    )
    
    # MySQL fields
    server: Optional[str] = Field(
        default=None,
        description="MySQL server hostname (required for mysql)"
    )
    port: Optional[int] = Field(
        default=None,
        ge=1, le=65535,
        description="MySQL/PostgreSQL server port (required for mysql/postgresql)"
    )
    username: Optional[str] = Field(
        default=None,
        description="MySQL username (required for mysql)"
    )
    password: Optional[str | SecretStr] = Field(
        default=None,
        description="MySQL password (can use !secret)"
    )
    time_zone: Optional[str] = Field(
        default=None,
        alias="time_zone",
        description="Database timezone"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )
    
    @model_validator(mode='after')
    def validate_engine_requirements(self) -> 'DatabaseConfig':
        """Validate engine-specific requirements."""
        if self.engine in ('mysql', 'postgresql'):
            if not self.server:
                raise ValueError(f"'server' is required when engine is '{self.engine}'")
            if not self.port:
                raise ValueError(f"'port' is required when engine is '{self.engine}'")
            if not self.username:
                raise ValueError(f"'username' is required when engine is '{self.engine}'")
        elif self.engine == 'sqlite':
            if not self.db_path and not self.database:
                raise ValueError("Either 'db_path' or 'database' is required for sqlite")
        
        return self
