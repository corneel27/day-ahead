"""Saving calculated prognoses after a change of interval (15min <-> 1hour)."""

import pandas as pd
import pytest
from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    select,
)

from dao.lib.db_manager import DBmanagerObj

T12 = 1_763_553_600  # a whole UTC hour
Q = 900
H = 3600


@pytest.fixture
def db():
    manager = DBmanagerObj.__new__(DBmanagerObj)
    manager.db_dialect = "sqlite"
    manager.engine = create_engine("sqlite:///:memory:")
    manager.metadata = MetaData()
    manager.log_pool_status = lambda: None
    metadata = MetaData()
    variabel = Table(
        "variabel", metadata,
        Column("id", Integer, primary_key=True), Column("code", String),
    )
    for name in ("prognoses", "values"):
        Table(
            name, metadata,
            Column("id", Integer, primary_key=True), Column("variabel", Integer),
            Column("time", Integer), Column("value", Float),
        )
    metadata.create_all(manager.engine)
    with manager.engine.begin() as connection:
        connection.execute(
            variabel.insert(),
            [{"id": 1, "code": "cons"}, {"id": 2, "code": "soc"}, {"id": 3, "code": "da"}],
        )
    yield manager
    manager.engine.dispose()


def save(db, code, rows, regrid=None, tablename="prognoses"):
    df = pd.DataFrame(
        [[str(t), code, v] for t, v in rows], columns=["time", "code", "value"]
    )
    db.savedata(df, tablename=tablename, regrid=regrid)


def stored(db, code, tablename="prognoses"):
    table = Table(tablename, MetaData(), autoload_with=db.engine)
    variabel = Table("variabel", MetaData(), autoload_with=db.engine)
    query = (
        select(table.c.time, table.c.value)
        .where(table.c.variabel == variabel.c.id, variabel.c.code == code)
        .order_by(table.c.time)
    )
    with db.engine.connect() as connection:
        return {int(r.time): r.value for r in connection.execute(query)}


def hour_sum(rows, hour):
    return sum(v for t, v in rows.items() if hour <= t < hour + H)


def quarters(start, hours, value=0.25):
    return [(start + i * Q, value) for i in range(4 * hours)]


def hours(start, count, value=1.0):
    return [(start + i * H, value) for i in range(count)]


def test_quarter_to_hour_removes_stale_quarters(db):
    save(db, "cons", quarters(T12, 4), regrid={})
    # hourly run starting exactly on 12:00
    save(db, "cons", hours(T12, 4, 2.0), regrid={})
    rows = stored(db, "cons")
    assert sorted(rows) == [T12 + i * H for i in range(4)]
    assert all(hour_sum(rows, T12 + i * H) == 2.0 for i in range(4))


def test_quarter_to_hour_mid_hour_merges_partial_hour(db):
    save(db, "cons", quarters(T12, 4), regrid={})
    # hourly run at 12:20: 12:00 is not saved, 13:00 onwards is
    save(db, "cons", hours(T12 + H, 3, 2.0), regrid={"first_start": T12})
    rows = stored(db, "cons")
    assert rows[T12] == pytest.approx(1.0)
    assert sorted(rows) == [T12 + i * H for i in range(4)]
    assert hour_sum(rows, T12 + H) == 2.0


def test_hour_to_quarter_mid_hour_splits_hourly_row(db):
    save(db, "cons", hours(T12, 4), regrid={})
    # quarter run at 12:20: 12:15 is not saved, 12:30 onwards is
    save(db, "cons", quarters(T12 + 2 * Q, 3)[:10], regrid={"first_start": T12 + Q})
    rows = stored(db, "cons")
    assert rows[T12] == pytest.approx(0.25)
    assert rows[T12 + Q] == pytest.approx(0.25)
    assert hour_sum(rows, T12) == pytest.approx(1.0)
    assert hour_sum(rows, T12 + H) == pytest.approx(1.0)
    # 15:00 lies beyond the new span and keeps its hourly value
    assert rows[T12 + 3 * H] == 1.0


def test_hour_to_quarter_first_row_saved(db):
    save(db, "cons", hours(T12, 2), regrid={})
    # pv_dc style: the partial first quarter 12:15 is saved itself
    save(db, "cons", quarters(T12 + Q, 1)[:3], regrid={})
    rows = stored(db, "cons")
    assert rows[T12] == pytest.approx(0.25)
    assert hour_sum(rows, T12) == pytest.approx(1.0)


def test_same_interval_changes_nothing_but_values(db):
    save(db, "cons", quarters(T12, 2), regrid={})
    # next quarter run at 12:20, skipping 12:15
    save(db, "cons", quarters(T12 + 2 * Q, 2, 0.5)[:6], regrid={"first_start": T12 + Q})
    rows = stored(db, "cons")
    assert rows[T12] == 0.25 and rows[T12 + Q] == 0.25
    assert hour_sum(rows, T12) == pytest.approx(1.5)
    assert len(rows) == 8


def test_hourly_prediction_part_then_quarters(db):
    # 15min run with an hourly predicted part from 13:00
    save(db, "cons", quarters(T12, 1) + hours(T12 + H, 2), regrid={})
    # later run with known quarter prices for 13:00-15:00
    save(db, "cons", quarters(T12 + H, 2), regrid={})
    rows = stored(db, "cons")
    assert hour_sum(rows, T12 + H) == pytest.approx(1.0)
    assert hour_sum(rows, T12 + 2 * H) == pytest.approx(1.0)


def test_state_codes_are_not_summed(db):
    save(db, "soc", [(T12 + i * Q, 50.0 + i) for i in range(9)], regrid={"state": True})
    save(db, "soc", [(T12 + i * H, 40.0 + i) for i in range(3)], regrid={"state": True})
    rows = stored(db, "soc")
    assert rows == {T12: 40.0, T12 + H: 41.0, T12 + 2 * H: 42.0}


def test_without_regrid_nothing_is_deleted(db):
    save(db, "da", quarters(T12, 1))
    save(db, "da", hours(T12, 1, 0.3))
    assert len(stored(db, "da")) == 4


def test_regrid_is_ignored_for_values(db):
    save(db, "da", quarters(T12, 1), tablename="values")
    save(db, "da", hours(T12, 1, 0.3), regrid={}, tablename="values")
    assert len(stored(db, "da", tablename="values")) == 4


def test_each_code_uses_its_own_times(db):
    save(db, "cons", quarters(T12, 1), regrid={})
    save(db, "soc", quarters(T12, 1, 50.0), regrid={})
    # cons has no value at 13:00, soc has: the stale cons quarters still go
    df = pd.DataFrame(
        [[str(T12), "cons", 1.0], [str(T12 + H), "cons", float("nan")],
         [str(T12), "soc", 40.0], [str(T12 + H), "soc", 41.0]],
        columns=["time", "code", "value"],
    )
    db.savedata(df, tablename="prognoses", regrid={})
    assert stored(db, "cons") == {T12: 1.0}


def test_single_time_keeps_later_rows(db):
    save(db, "cons", quarters(T12, 1), regrid={})
    save(db, "cons", [(T12, 0.3)], regrid={})
    assert len(stored(db, "cons")) == 4
