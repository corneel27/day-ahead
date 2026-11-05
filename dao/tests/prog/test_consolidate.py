"""Check consolidate_data against an isolated SQLite database."""

import datetime as dt
import threading
import time

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
from dao.prog.da_report import Report

DAY = dt.datetime(2026, 1, 14)
CODES = ["cons", "prod", "cost", "profit"]


@pytest.fixture
def report():
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
    Table(
        "values", metadata,
        Column("id", Integer, primary_key=True), Column("variabel", Integer),
        Column("time", Integer), Column("value", Float),
    )
    metadata.create_all(manager.engine)
    with manager.engine.begin() as connection:
        connection.execute(
            variables.insert(), [{"id": i + 1, "code": c} for i, c in enumerate(CODES)]
        )

    rep = Report.__new__(Report)
    rep.db_da = manager
    rep.grid_dict = {
        "cons": {"sensors": ["sensor.cons"]},
        "prod": {"sensors": ["sensor.prod"]},
        "cost": {"sensors": "calc", "function": "calc_cost"},
        "profit": {"sensors": "calc", "function": "calc_cost"},
    }
    energy = {"cons": [1.0, 2.0, 3.0], "prod": [0.5, 0.0, 1.5]}

    def get_sensor_sum(sensor_list, vanaf, tot, col_name):
        hours = [DAY + dt.timedelta(hours=h) for h in range(3)]
        rows = [(t, v) for t, v in zip(hours, energy[col_name], strict=True) if vanaf <= t < tot]
        df = pd.DataFrame(rows, columns=["tijd", col_name])
        df.index = pd.to_datetime(df["tijd"])
        return df

    def get_price_data(vanaf, tot):
        hours = [DAY + dt.timedelta(hours=h) for h in range(3)]
        return pd.DataFrame(
            {"time": hours, "da_cons": [0.2, 0.3, 0.4], "da_prod": [0.1, 0.1, 0.2]}
        )

    rep.get_sensor_sum = get_sensor_sum
    rep.get_price_data = get_price_data
    yield rep
    manager.engine.dispose()


def stored(rep):
    values = Table("values", MetaData(), autoload_with=rep.db_da.engine)
    variabel = Table("variabel", MetaData(), autoload_with=rep.db_da.engine)
    query = select(variabel.c.code, values.c.time, values.c.value).where(
        values.c.variabel == variabel.c.id
    )
    with rep.db_da.engine.connect() as connection:
        rows = connection.execute(query).all()
    result = {}
    for code, moment, value in rows:
        result.setdefault(code, {})[dt.datetime.fromtimestamp(moment).hour] = value
    return result


def test_consolidate_saves_energy_cost_and_profit(report):
    report.consolidate_data(DAY, DAY + dt.timedelta(days=1))
    data = stored(report)
    assert data["cons"] == {0: 1.0, 1: 2.0, 2: 3.0}
    assert data["prod"] == {0: 0.5, 1: 0.0, 2: 1.5}
    assert data["cost"] == pytest.approx({0: 0.2, 1: 0.6, 2: 1.2})
    assert data["profit"] == pytest.approx({0: 0.05, 1: 0.0, 2: 0.3})


def test_latest_present_is_the_newest_record(report):
    report.consolidate_data(DAY, DAY + dt.timedelta(days=1))
    assert report.get_latest_present("cons") == DAY + dt.timedelta(hours=2)
    assert report.get_latest_present("cost") == DAY + dt.timedelta(hours=2)


def test_rerun_continues_after_latest_record(report):
    report.consolidate_data(DAY, DAY + dt.timedelta(hours=2))
    assert sorted(stored(report)["cost"]) == [0, 1]
    report.consolidate_data(None, DAY + dt.timedelta(days=1))
    assert stored(report)["cost"] == pytest.approx({0: 0.2, 1: 0.6, 2: 1.2})


@pytest.fixture
def amsterdam(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Amsterdam")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_repeated_dst_hour_keeps_both_occurrences(report, amsterdam):
    # 2026-10-25: de klok gaat van 03:00 terug naar 02:00
    first = int(dt.datetime(2026, 10, 25, 2, fold=0).timestamp())
    second = first + 3600
    tijd = [dt.datetime(2026, 10, 25, 2)] * 2

    def get_sensor_sum(sensor_list, vanaf, tot, col_name):
        df = pd.DataFrame({"tijd": tijd, col_name: [1.0, 2.0]})
        df.index = pd.to_datetime(df["tijd"])
        return df

    def get_price_data(vanaf, tot):
        return pd.DataFrame({"time": tijd[:1], "da_cons": [0.5], "da_prod": [0.1]})

    report.get_sensor_sum = get_sensor_sum
    report.get_price_data = get_price_data
    report.consolidate_data(dt.datetime(2026, 10, 25), dt.datetime(2026, 10, 26))
    values = Table("values", MetaData(), autoload_with=report.db_da.engine)
    with report.db_da.engine.connect() as connection:
        rows = connection.execute(
            select(values.c.variabel, values.c.time, values.c.value)
        ).all()
    by_code = {}
    for variabel, moment, value in rows:
        by_code.setdefault(CODES[variabel - 1], {})[moment] = value
    assert by_code["cons"] == {first: 1.0, second: 2.0}
    assert by_code["cost"] == pytest.approx({first: 0.5, second: 1.0})
