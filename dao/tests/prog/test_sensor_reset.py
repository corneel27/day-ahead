"""Energy read from HA long-term statistics across meter resets."""

import datetime as dt

import pytest
from sqlalchemy import Column, Double, Integer, MetaData, String, Table

from dao.lib.db_manager import DBmanagerObj
from dao.prog.da_report import Report

START = dt.datetime(2026, 1, 5)  # a Monday, local time
HOUR = 3600

# Readings at the end of each hour (state) and HA's running total (sum).
# The meter resets during the 4th hour: 1 kWh is used every hour.
RESET_STATE = [10.0, 11.0, 12.0, 0.5, 1.5, 2.5]
RESET_SUM = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def make_report(tmp_path, with_sum=True):
    db_ha = DBmanagerObj("sqlite", "ha.db", db_path=str(tmp_path))
    md = MetaData()
    columns = [
        Column("id", Integer, primary_key=True),
        Column("metadata_id", Integer),
        Column("start_ts", Double),
        Column("state", Double),
        Column("mean", Double),
    ]
    if with_sum:
        columns.append(Column("sum", Double))
    statistics = Table("statistics", md, *columns)
    meta = Table(
        "statistics_meta",
        md,
        Column("id", Integer, primary_key=True),
        Column("statistic_id", String(255)),
        Column("unit_of_measurement", String(255)),
    )
    md.create_all(db_ha.engine)
    with db_ha.engine.begin() as connection:
        connection.execute(
            meta.insert(),
            [
                {"id": 1, "statistic_id": "sensor.reset", "unit_of_measurement": "kWh"},
                {
                    "id": 2,
                    "statistic_id": "sensor.no_sum",
                    "unit_of_measurement": "kWh",
                },
                {"id": 3, "statistic_id": "sensor.mixed", "unit_of_measurement": "Wh"},
            ],
        )
    report = Report.__new__(Report)
    report.db_ha = db_ha
    return report, statistics


def insert(report, statistics, metadata_id, states, sums=None):
    first = START.timestamp() - HOUR
    rows = []
    for i, state in enumerate(states):
        row = {"metadata_id": metadata_id, "start_ts": first + i * HOUR, "state": state}
        if sums is not None:
            row["sum"] = sums[i]
        rows.append(row)
    with report.db_ha.engine.begin() as connection:
        connection.execute(statistics.insert(), rows)


def hourly(report, sensor, hours):
    df = report.get_sensor_data(
        sensor, START, START + dt.timedelta(hours=hours), "kwh", agg="uur"
    )
    return [float(v) for v in df["kwh"]]


def test_sum_survives_reset(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 1, RESET_STATE, RESET_SUM)
    assert hourly(report, "sensor.reset", 5) == pytest.approx([1.0] * 5)


def test_daily_aggregate_survives_reset(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 1, RESET_STATE, RESET_SUM)
    df = report.get_sensor_data(
        "sensor.reset", START, START + dt.timedelta(days=1), "kwh", agg="dag"
    )
    assert df["kwh"].sum() == pytest.approx(5.0)


def test_state_used_without_sum_values(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 2, [10.0, 11.0, 13.0, 12.0], [None] * 4)
    # a drop of the state counts as zero, as before
    assert hourly(report, "sensor.no_sum", 3) == pytest.approx([1.0, 2.0, 0.0])


def test_state_used_when_one_sum_is_missing(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(
        report,
        statistics,
        3,
        [1000.0, 2000.0, 4000.0, 5000.0],
        [0.0, None, 3000.0, 4000.0],
    )
    assert hourly(report, "sensor.mixed", 3) == pytest.approx([1.0, 2.0, 1.0])


def test_decreasing_sum_counts_as_zero(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 1, [5.0, 6.0, 4.0], [5.0, 6.0, 4.0])
    assert hourly(report, "sensor.reset", 2) == pytest.approx([1.0, 0.0])


def test_table_without_sum_column(tmp_path):
    report, statistics = make_report(tmp_path, with_sum=False)
    insert(report, statistics, 1, RESET_STATE)
    assert hourly(report, "sensor.reset", 5) == pytest.approx([1.0, 1.0, 0.0, 1.0, 1.0])


def test_week_data_survives_reset(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 1, RESET_STATE, RESET_SUM)
    df = report.get_sensor_week_data(
        "sensor.reset",
        START.weekday(),
        START,
        START + dt.timedelta(days=1),
        "kwh",
    )
    assert list(df["kwh"]) == pytest.approx([1.0] * 5)
    assert list(df["uur"]) == [0, 1, 2, 3, 4]


def test_week_data_without_sum_values(tmp_path):
    report, statistics = make_report(tmp_path)
    insert(report, statistics, 3, [1000.0, 3000.0, 2000.0], [None] * 3)
    df = report.get_sensor_week_data(
        "sensor.mixed",
        START.weekday(),
        START,
        START + dt.timedelta(days=1),
        "kwh",
    )
    assert list(df["kwh"]) == pytest.approx([2.0, 0.0])
