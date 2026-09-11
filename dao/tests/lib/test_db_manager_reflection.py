"""
Tests for the thread safety of table reflection in DBmanagerObj.

The webserver serves requests from multiple threads while sharing a single
DBmanagerObj (and therefore a single SQLAlchemy MetaData) per process.
Reflecting a table registers it in the MetaData before its columns are read
from the database, so concurrent reflection used to hand a thread a table
without columns.
"""

import threading

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

from dao.lib.db_manager import DBmanagerObj


@pytest.fixture
def db_da(tmp_path):
    """A DBmanagerObj on an empty sqlite database with the day ahead tables."""
    db_name = "day_ahead.db"
    db = DBmanagerObj(
        db_dialect="sqlite",
        db_name=db_name,
        db_path=str(tmp_path),
    )
    metadata = MetaData()
    Table(
        "variabel",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("code", String(10), unique=True, nullable=False),
        Column("name", String(50), unique=True, nullable=False),
        Column("dim", String(10), nullable=False),
    )
    Table(
        "values",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(
            "variabel",
            Integer,
            ForeignKey("variabel.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("time", BigInteger, nullable=False),
        Column("value", Float),
        UniqueConstraint("variabel", "time"),
    )
    metadata.create_all(db.engine)
    return db


def test_get_table_reflects_columns(db_da):
    values_table = db_da.get_table("values")
    assert {"id", "variabel", "time", "value"} <= set(values_table.c.keys())


def test_get_table_is_cached(db_da):
    assert db_da.get_table("values") is db_da.get_table("values")


def test_get_table_accepts_a_connection_as_bind(db_da):
    with db_da.engine.connect() as connection:
        variabel_table = db_da.get_table("variabel", bind=connection)
    assert "code" in variabel_table.c


def test_get_table_replaces_an_empty_table_in_the_metadata(db_da):
    """A table left behind without columns is reflected again, not returned."""
    Table("values", db_da.metadata)
    assert len(db_da.metadata.tables["values"].columns) == 0

    values_table = db_da.get_table("values")

    assert "time" in values_table.c


def test_concurrent_get_table_returns_usable_tables(db_da):
    """Reflecting from several threads at once must not yield empty tables."""
    errors = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            values_table = db_da.get_table("values")
            variabel_table = db_da.get_table("variabel")
            # Aliases build their own column collection from the table, which
            # is where an incompletely reflected table used to surface.
            assert values_table.alias("t1").c.time is not None
            assert variabel_table.alias("v1").c.id is not None
        except Exception as ex:  # noqa: BLE001 - reported through `errors`
            errors.append(ex)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
