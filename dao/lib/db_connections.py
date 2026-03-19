"""
DB connection factories.

Accepts a validated ``ConfigurationV0`` model plus a resolved secrets dict
and constructs a ``DBmanagerObj``.  No caching is done here — callers should
store and reuse the returned object (e.g. on ``self.db_da``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from dao.lib.db_manager import DBmanagerObj
from dao.prog.config.models.base import SecretStr

if TYPE_CHECKING:
    # Never imported at runtime — only used for static type hints in function signatures.
    # from __future__ import annotations (above) makes annotations lazy strings,
    # so ConfigurationV0 is never resolved at runtime.
    from dao.prog.config.versions.v0 import ConfigurationV0

logger = logging.getLogger(__name__)


def _resolve_password(pw: Optional[SecretStr], secrets: dict) -> Optional[str]:
    """Resolve a SecretStr reference to its plain-text value."""
    if pw is None:
        return None
    return pw.resolve(secrets)


def make_db_da(
    config: ConfigurationV0,
    secrets: dict,
    check_create: bool = False,
) -> Optional[DBmanagerObj]:
    """
    Build a DB connection for the Day Ahead database.

    Args:
        config: Validated ConfigurationV0 instance.
        secrets: Loaded secrets dict (from ConfigurationLoader.secrets).
        check_create: If True and the database does not exist, create it.

    Returns:
        DBmanagerObj instance, or None on error.
    """
    db = config.database_da
    engine = db.engine  # model default: "sqlite"
    server = db.server
    port = db.port
    db_name = db.database
    username = db.username
    password = _resolve_password(db.password, secrets)
    db_path = db.db_path
    time_zone = config.time_zone

    if check_create:
        import sqlalchemy_utils

        db_url = DBmanagerObj.db_url(
            db_dialect=engine,
            db_name=db_name,
            db_server=server,
            db_user=username,
            db_password=password,
            db_port=port,
            db_path=db_path,
        )
        if not sqlalchemy_utils.database_exists(db_url):
            sqlalchemy_utils.create_database(db_url)

    try:
        return DBmanagerObj(
            db_dialect=engine,
            db_name=db_name,
            db_server=server,
            db_user=username,
            db_password=password,
            db_port=port,
            db_path=db_path,
            db_time_zone=time_zone,
        )
    except ConnectionAbortedError:
        if db.engine == "sqlite":
            logger.error(f"day_ahead database not found: {db.db_path}/{db.database}")
        else:
            logger.error(f"day_ahead database not found on {db.engine} server {db.server}")
        return None
    except Exception as ex:
        logger.error(f"Cannot connect to day_ahead database ({db.engine}): {ex}")
        return None


def make_db_ha(
    config: ConfigurationV0,
    secrets: dict,
) -> Optional[DBmanagerObj]:
    """
    Build a DB connection for the Home Assistant database.

    Args:
        config: Validated ConfigurationV0 instance.
        secrets: Loaded secrets dict (from ConfigurationLoader.secrets).

    Returns:
        DBmanagerObj instance, or None on error.
    """
    db = config.database_ha
    engine = db.engine  # model default: "mysql"
    server = db.server
    port = db.port
    db_name = db.database
    username = db.username
    password = _resolve_password(db.password, secrets)
    db_path = db.db_path
    time_zone = config.time_zone

    try:
        return DBmanagerObj(
            db_dialect=engine,
            db_name=db_name,
            db_server=server,
            db_user=username,
            db_password=password,
            db_port=port,
            db_path=db_path,
            db_time_zone=time_zone,
        )
    except ConnectionAbortedError:
        if db.engine == "sqlite":
            logger.error(f"Home Assistant database not found: {db.db_path}/{db.database}")
        else:
            logger.error(f"Home Assistant database not found on {db.engine} server {db.server}")
        return None
    except Exception as ex:
        logger.error(f"Cannot connect to Home Assistant database ({db.engine}): {ex}")
        return None
