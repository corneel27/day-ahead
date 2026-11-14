"""Hours without HA statistics must not reach the ML solar training as 0 kWh."""

import datetime as dt

import pytest
from sqlalchemy import Column, Double, Integer, MetaData, String, Table

from dao.lib.db_manager import DBmanagerObj
from dao.prog import da_report, solar_predictor
from dao.prog.da_report import Report

START = dt.datetime(2026, 1, 5)  # local time
HOUR = 3600
SENSOR = "sensor.pv_energy"

# Meter readings at the end of each hour, keyed by the hour counted from
# START. Hour -1 is the reading the first hour is measured against. Hours 4
# to 7 have no statistics at all; the meter kept counting in the meantime.
READINGS = {-1: 100.0, 0: 101.0, 1: 103.0, 2: 106.0, 3: 106.5, 8: 120.0, 9: 121.0, 10: 123.0}
HOURS = 11


def make_report(tmp_path):
    db_ha = DBmanagerObj("sqlite", "ha.db", db_path=str(tmp_path))
    md = MetaData()
    statistics = Table(
        "statistics",
        md,
        Column("id", Integer, primary_key=True),
        Column("metadata_id", Integer),
        Column("start_ts", Double),
        Column("state", Double),
        Column("mean", Double),
        Column("sum", Double),
    )
    meta = Table(
        "statistics_meta",
        md,
        Column("id", Integer, primary_key=True),
        Column("statistic_id", String(255)),
        Column("unit_of_measurement", String(255)),
    )
    md.create_all(db_ha.engine)
    first = READINGS[-1]
    with db_ha.engine.begin() as connection:
        connection.execute(
            meta.insert(),
            [{"id": 1, "statistic_id": SENSOR, "unit_of_measurement": "kWh"}],
        )
        connection.execute(
            statistics.insert(),
            [
                {
                    "metadata_id": 1,
                    "start_ts": START.timestamp() + hour * HOUR,
                    "state": state,
                    "sum": state - first,
                }
                for hour, state in READINGS.items()
            ],
        )
    report = Report.__new__(Report)
    report.db_ha = db_ha
    return report


def by_hour(df, col_name):
    return {
        round((tijd - START).total_seconds() / HOUR): float(value)
        for tijd, value in zip(df["tijd"], df[col_name], strict=True)
    }


def test_missing_hours_are_filled_with_zero_by_default(tmp_path):
    report = make_report(tmp_path)
    df = report.get_sensor_data(
        SENSOR, START, START + dt.timedelta(hours=HOURS), "kwh", agg="uur"
    )
    assert by_hour(df, "kwh") == pytest.approx(
        {0: 1.0, 1: 2.0, 2: 3.0, 3: 0.5, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 1.0, 10: 2.0}
    )


def test_missing_hours_are_left_out_on_request(tmp_path):
    report = make_report(tmp_path)
    df = report.get_sensor_data(
        SENSOR,
        START,
        START + dt.timedelta(hours=HOURS),
        "kwh",
        agg="uur",
        fill_missing=False,
    )
    # hour 8 is left out as well: its reading follows the gap, so there is
    # nothing to measure it against
    assert by_hour(df, "kwh") == pytest.approx(
        {0: 1.0, 1: 2.0, 2: 3.0, 3: 0.5, 9: 1.0, 10: 2.0}
    )


def test_training_data_has_no_rows_for_missing_hours(tmp_path, monkeypatch):
    report = make_report(tmp_path)
    monkeypatch.setattr(da_report, "Report", lambda: report)
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)

    solar_data = predictor.get_solar_data(START, [SENSOR])

    hours = sorted(
        round((ts.timestamp() - START.timestamp()) / HOUR) for ts in solar_data.index
    )
    assert hours == [0, 1, 2, 3, 9, 10]
    assert solar_data["solar_kwh"].tolist() == pytest.approx(
        [1.0, 2.0, 3.0, 0.5, 1.0, 2.0]
    )


def test_resampling_keeps_missing_hours_out_of_the_training_set(tmp_path, monkeypatch):
    report = make_report(tmp_path)
    monkeypatch.setattr(da_report, "Report", lambda: report)
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    solar_data = predictor.get_solar_data(START, [SENSOR])

    solar_df = predictor._load_and_process_solar_data(solar_data).dropna()

    assert len(solar_df) == 6
    assert solar_df["solar_kwh"].tolist() == pytest.approx(
        [1.0, 2.0, 3.0, 0.5, 1.0, 2.0]
    )
