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
        description="Database engine type",
        json_schema_extra={
            "x-help": "Database engine where Home Assistant stores history data. Most HA installations use SQLite, but MySQL/MariaDB and PostgreSQL are also supported.",
            "x-category": "basic"
        }
    )
    server: Optional[str] = Field(
        default=None,
        description="Database server hostname (required for mysql/postgresql)",
        json_schema_extra={
            "x-help": "Hostname or IP address of database server. Required for MySQL/PostgreSQL, not used for SQLite. Examples: 'localhost', '192.168.1.100', 'mysql.local'.",
            "x-category": "basic",
            "x-validation-hint": "Required for mysql/postgresql engines"
        }
    )
    port: Optional[int] = Field(
        default=None,
        ge=1, le=65535,
        description="Database port",
        json_schema_extra={
            "x-help": "Database server port. If not specified, defaults to 3306 for MySQL or 5432 for PostgreSQL. Not used for SQLite.",
            "x-unit": "port",
            "x-category": "basic",
            "x-validation-hint": "1-65535, defaults: mysql=3306, postgresql=5432"
        }
    )
    database: str = Field(
        default="homeassistant",
        description="Database name",
        json_schema_extra={
            "x-help": "Name of the Home Assistant database. Default 'homeassistant' matches standard HA installation.",
            "x-category": "basic"
        }
    )
    username: str = Field(
        default="homeassistant",
        description="Database username",
        json_schema_extra={
            "x-help": "Username for database authentication. Default 'homeassistant' matches standard HA installation.",
            "x-category": "basic"
        }
    )
    password: Optional[str | SecretStr] = Field(
        default=None,
        description="Database password (can use !secret)",
        json_schema_extra={
            "x-help": "Database password. Use secrets.json with '!secret password_key' pattern for security. Never store passwords directly in config.",
            "x-category": "basic",
            "x-validation-hint": "Use !secret for passwords"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',  # Preserve unknown keys
        populate_by_name=True,
        json_schema_extra={
            "x-help": "Home Assistant database connection for reading historical sensor data (prices, solar, baseload).",
            "x-category": "infrastructure"
        }
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
        description="Database engine type",
        json_schema_extra={
            "x-help": "Database engine for Day Ahead optimizer data. SQLite is simplest (no server needed), MySQL/PostgreSQL for advanced setups or shared databases.",
            "x-category": "basic"
        }
    )
    
    # SQLite fields
    db_path: Optional[str] = Field(
        default=None,
        description="Database path for SQLite (e.g., '../data')",
        json_schema_extra={
            "x-help": "Directory path for SQLite database file. Relative to add-on root. Example: '../data' stores in persistent data folder. Only for SQLite.",
            "x-category": "basic",
            "x-validation-hint": "Required for SQLite (or use database field)"
        }
    )
    database: Optional[str] = Field(
        default=None,
        description="Database filename for SQLite or database name for MySQL",
        json_schema_extra={
            "x-help": "For SQLite: filename (e.g., 'day_ahead.db'). For MySQL/PostgreSQL: database name. At least one of db_path or database required for SQLite.",
            "x-category": "basic",
            "x-validation-hint": "Filename for SQLite, database name for MySQL/PostgreSQL"
        }
    )
    
    # MySQL fields
    server: Optional[str] = Field(
        default=None,
        description="MySQL server hostname (required for mysql)",
        json_schema_extra={
            "x-help": "Hostname or IP of MySQL/PostgreSQL server. Required for server-based engines. Examples: 'localhost', '192.168.1.100'.",
            "x-category": "advanced",
            "x-validation-hint": "Required for mysql/postgresql engines"
        }
    )
    port: Optional[int] = Field(
        default=None,
        ge=1, le=65535,
        description="MySQL/PostgreSQL server port (required for mysql/postgresql)",
        json_schema_extra={
            "x-help": "Database server port. Required for MySQL/PostgreSQL. Standard ports: 3306 (MySQL), 5432 (PostgreSQL).",
            "x-unit": "port",
            "x-category": "advanced",
            "x-validation-hint": "1-65535, required for mysql/postgresql"
        }
    )
    username: Optional[str] = Field(
        default=None,
        description="MySQL username (required for mysql)",
        json_schema_extra={
            "x-help": "Database username for authentication. Required for MySQL/PostgreSQL.",
            "x-category": "advanced",
            "x-validation-hint": "Required for mysql/postgresql engines"
        }
    )
    password: Optional[str | SecretStr] = Field(
        default=None,
        description="MySQL password (can use !secret)",
        json_schema_extra={
            "x-help": "Database password. Use secrets.json with '!secret password_key' for security. Never store passwords directly in config.",
            "x-category": "advanced",
            "x-validation-hint": "Use !secret for passwords"
        }
    )
    time_zone: Optional[str] = Field(
        default=None,
        alias="time_zone",
        description="Database timezone",
        json_schema_extra={
            "x-help": "Optional: Timezone for database timestamps. Examples: 'Europe/Amsterdam', 'UTC'. Usually not needed if database and system timezones match.",
            "x-category": "expert"
        }
    )
    
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
        json_schema_extra={
            'x-ui-group': 'Infrastructure',
            'x-icon': 'database',
            'x-order': 10,
            'x-help': '''# Day Ahead Database Configuration

Database for storing Day Ahead optimizer calculations, schedules, and results.

## Engine Options

### SQLite (Recommended for most users)
- **Pros**: No server setup, simple, included with Home Assistant
- **Cons**: Single-user, not suitable for multiple HA instances
- **Config**: Specify db_path and/or database filename

### MySQL/MariaDB
- **Pros**: Multi-user, robust, good performance
- **Cons**: Requires separate database server
- **Config**: server, port, username, password, database name

### PostgreSQL
- **Pros**: Advanced features, excellent for large datasets
- **Cons**: Requires separate database server, more complex
- **Config**: server, port, username, password, database name

## Security

**Never store passwords in options.json!**

Use secrets.json:
```json
{
  "db_password": "actual_password_here"
}
```

Then in options.json:
```json
"password": "!secret db_password"
```

## Tips

- SQLite for single HA instance (simplest)
- MySQL for shared database or multiple instances
- Use strong passwords for server-based databases
- Ensure database is backed up (contains optimization history)
- Check database size periodically (can grow with history)
''',
            'x-docs-url': 'https://github.com/corneel27/day-ahead/wiki/Database-Configuration',
            'x-category': 'infrastructure',
            'x-collapsible': True
        }
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
