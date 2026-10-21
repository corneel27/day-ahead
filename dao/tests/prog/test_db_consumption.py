"""Check consumption windows against an isolated SQLite database."""

import datetime as dt
import threading

import pytest
from freezegun import freeze_time
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine

from dao.lib.db_manager import DBmanagerObj


@pytest.fixture
def database():
    # Isolate the query from platform-specific URL construction and real files.
    manager = DBmanagerObj.__new__(DBmanagerObj)
    manager.db_dialect = "sqlite"
    manager.engine = create_engine("sqlite:///:memory:")
    manager.metadata = MetaData()
    manager._metadata_lock = threading.RLock()
    metadata = MetaData()
    variables = Table(
        "variabel", metadata,
        Column("id", Integer, primary_key=True), Column("code", String),
    )
    values = Table(
        "values", metadata,
        Column("id", Integer, primary_key=True), Column("variabel", Integer),
        Column("time", Integer), Column("value", Float),
    )
    metadata.create_all(manager.engine)
    with manager.engine.begin() as connection:
        connection.execute(variables.insert(), [{"id": 1, "code": "cons"}, {"id": 2, "code": "prod"}])
        rows = []
        for hour, consumed, produced in [(1, 1.0, 0.5), (3, 3.0, 1.5)]:
            # Query boundaries are local wall times, converted to UTC by SQLite.
            timestamp = int(dt.datetime(2026, 1, 14, hour).timestamp())
            rows.extend([
                {"variabel": 1, "time": timestamp, "value": consumed},
                {"variabel": 2, "time": timestamp, "value": produced},
            ])
        connection.execute(values.insert(), rows)
    yield manager
    manager.engine.dispose()


def test_default_end_tracks_each_call(database):
    start = dt.datetime(2026, 1, 14)
    with freeze_time("2026-01-14 02:00:00"):
        first = database.get_consumption(start)
    with freeze_time("2026-01-14 05:00:00"):
        second = database.get_consumption(start)
    assert first == {"consumption": 1.0, "production": 0.5}
    assert second == {"consumption": 4.0, "production": 2.0}


def test_explicit_end_is_preserved(database):
    with freeze_time("2026-01-14 05:00:00"):
        result = database.get_consumption(dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 14, 2))
    assert result == {"consumption": 1.0, "production": 0.5}
