"""Exercise database startup with SQLite and explicitly enabled disposable servers."""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy_utils
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from dao.lib.db_connections import _build_db_da, _build_db_ha
from dao.lib.db_manager import DBmanagerObj


@pytest.fixture(params=["sqlite", "mariadb", "postgresql"])
def database(request, tmp_path):
    backend = request.param
    options = {"engine": "sqlite", "database": "review.db", "db_path": str(tmp_path),
               "server": None, "username": None, "password": None, "port": 0}
    if backend != "sqlite":
        value = os.getenv(f"DAO_TEST_{backend.upper()}_URL")
        if not value or os.getenv("DAO_TEST_ALLOW_SCHEMA_RESET") != "1":
            pytest.skip("disposable database not explicitly enabled")
        server = make_url(value)
        dialect = "mysql" if backend == "mariadb" else "postgresql"
        if server.database != "dao_query_test" or server.get_backend_name() != dialect:
            raise ValueError("Database fixtures require the dedicated dao_query_test configuration")
        # Only this test's uniquely named database may be created or dropped.
        options.update(engine=dialect, database="dao_dependency_" + uuid4().hex,
                       server=server.host, port=server.port or (3306 if dialect == "mysql" else 5432),
                       username=server.username,
                       password=SimpleNamespace(resolve=lambda secrets: server.password))
    config = SimpleNamespace(database_da=SimpleNamespace(**options),
                             database_ha=SimpleNamespace(**options), time_zone="Europe/Amsterdam")
    url = DBmanagerObj.db_url(
        db_dialect=options["engine"], db_name=options["database"], db_path=options["db_path"],
        db_server=options["server"], db_user=options["username"], db_port=options["port"],
        db_password=options["password"].resolve({}) if options["password"] else None,
    )
    try:
        yield SimpleNamespace(config=config, url=url)
    finally:
        if backend != "sqlite":
            assert options["database"].startswith("dao_dependency_")
            if sqlalchemy_utils.database_exists(url):
                sqlalchemy_utils.drop_database(url)


def test_database_helpers_import():
    assert callable(sqlalchemy_utils.database_exists)
    assert callable(sqlalchemy_utils.create_database)


def test_da_bootstrap_creates_a_usable_database(database):
    manager = _build_db_da(database.config, {}, check_create=True)
    assert manager is not None
    try:
        with manager.engine.begin() as connection:
            connection.execute(text("CREATE TABLE bootstrap_probe (value INTEGER)"))
            connection.execute(text("INSERT INTO bootstrap_probe VALUES (42)"))
        with manager.engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM bootstrap_probe")) == 42
    finally:
        manager.engine.dispose()


@pytest.mark.parametrize("factory", [_build_db_da, _build_db_ha], ids=["dao", "ha"])
def test_missing_database_is_not_silently_created(database, factory):
    assert factory(database.config, {}) is None
    assert not sqlalchemy_utils.database_exists(database.url)


@pytest.mark.parametrize("factory", [_build_db_da, _build_db_ha], ids=["dao", "ha"])
def test_existing_database_preserves_rows(database, factory):
    sqlalchemy_utils.create_database(database.url)
    engine = create_engine(database.url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE preserved_data (value INTEGER)"))
            connection.execute(text("INSERT INTO preserved_data VALUES (17)"))
    finally:
        engine.dispose()
    manager = factory(database.config, {})
    assert manager is not None
    try:
        with manager.engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM preserved_data")) == 17
    finally:
        manager.engine.dispose()


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_network_databases_have_driver_timeouts(dialect):
    args = DBmanagerObj.connect_args(dialect)
    assert args["connect_timeout"] > 0
    if dialect == "mysql":
        assert args["read_timeout"] > 0 and args["write_timeout"] > 0
    else:
        assert args["keepalives"] == 1


def test_sqlite_has_no_driver_timeouts():
    assert DBmanagerObj.connect_args("sqlite") == {}
