"""
Database configuration models.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .base import SecretStr


class HADatabaseConfig(BaseModel):
    """Home Assistant database connection configuration."""
    
    engine: Literal["mysql", "sqlite", "postgresql"] = Field(
        default="mysql",
        description="Database engine type"
    )
    server: Optional[str] = Field(
        default="core-mariadb",
        description="Database server hostname (required for mysql/postgresql)"
    )
    port: Optional[int] = Field(
        default=None,
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
    
    @field_validator('port', mode='before')
    @classmethod
    def set_default_port(cls, v: Optional[int], info) -> Optional[int]:
        """Set default port based on engine if not specified."""
        if v is not None:
            return v
        
        # Get engine from validation context
        engine = info.data.get('engine', 'mysql')
        if engine == 'mysql':
            return 3306
        elif engine == 'postgresql':
            return 5432
        return None  # SQLite doesn't use port
    
    @field_validator('server', mode='after')
    @classmethod
    def validate_server_required(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure server is provided for mysql/postgresql."""
        engine = info.data.get('engine', 'mysql')
        if engine in ('mysql', 'postgresql') and not v:
            raise ValueError(f"'server' is required for {engine} database")
        return v


class MySQLDatabaseConfig(BaseModel):
    """MySQL-specific database configuration (for optimization database)."""
    
    server: str = Field(
        default="localhost",
        description="MySQL server hostname"
    )
    port: int = Field(
        default=3306,
        description="MySQL server port"
    )
    database: str = Field(
        default="day_ahead",
        description="Database name for optimization data"
    )
    username: str = Field(
        default="day_ahead_user",
        description="Database username"
    )
    password: str | SecretStr = Field(
        description="Database password (can use !secret)"
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )


class DatabaseConfig(BaseModel):
    """
    Day Ahead database configuration (database da).
    
    Can be either SQLite or MySQL/MariaDB.
    """
    
    engine: str = Field(
        default="sqlite",
        description="Database engine: 'sqlite' | 'mysql'"
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
        description="MySQL server hostname"
    )
    port: Optional[int] = Field(
        default=None,
        description="MySQL server port"
    )
    username: Optional[str] = Field(
        default=None,
        description="MySQL username"
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
