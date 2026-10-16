"""Exercise report source and forecast boundaries with isolated SQLite data."""

import datetime as dt
import threading
from unittest.mock import Mock

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
    event,
)

from dao.lib.db_manager import DBmanagerObj
from dao.prog.da_report import Report


@pytest.mark.parametrize("source", ["all", "da", "ha"])
@pytest.mark.parametrize("complete", [False, True])
def test_forecasts_only_fill_unfinished_da_or_combined_reports(source, complete):
    start = dt.datetime(2026, 1, 14)
    end = start + dt.timedelta(hours=2)
    recorded_hours = 2 if complete else 1
    manager = DBmanagerObj.__new__(DBmanagerObj)
    manager.db_dialect = "sqlite"
    manager.engine = create_engine("sqlite:///:memory:")
    manager.metadata = MetaData()
    manager._metadata_lock = threading.RLock()
    metadata = MetaData()
    variables = Table("variabel", metadata, Column("id", Integer, primary_key=True), Column("code", String))
    values = Table("values", metadata, Column("time", Integer), Column("variabel", Integer), Column("value", Float))
    forecasts = Table("prognoses", metadata, Column("time", Integer), Column("variabel", Integer), Column("value", Float))
    metadata.create_all(manager.engine)
    queries = []

    def record_query(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    report = Report.__new__(Report)
    report.db_da = manager
    report.interval = "1hour"
    report.grid_consumption_sensors = ["sensor.consumption"]
    report.grid_production_sensors = ["sensor.production"]
    times = [start + dt.timedelta(hours=hour) for hour in range(recorded_hours)]

    def sensor_data(sensor, *args):
        column = "consumption" if sensor == "sensor.consumption" else "production"
        return pd.DataFrame({"tijd": times, column: [2.0 if column == "consumption" else 0.5] * len(times)})

    def price_data(vanaf, tot, **kwargs):
        price_times = [moment for moment in (start, start + dt.timedelta(hours=1)) if vanaf <= moment < tot]
        return pd.DataFrame({"time": price_times,
                             "da_cons": [0.25] * len(price_times), "da_prod": [0.1] * len(price_times)})

    report.get_sensor_data = Mock(side_effect=sensor_data)
    report.get_price_data = Mock(side_effect=price_data)
    try:
        with manager.engine.begin() as connection:
            connection.execute(variables.insert(), [
                {"id": index, "code": code}
                for index, code in enumerate(("cons", "prod", "cost", "profit"), start=1)
            ])
            # DA-only reports take recorded values from SQLite; other sources
            # obtain them from the isolated HA sensor stub above.
            if source == "da":
                connection.execute(values.insert(), [
                    {"time": int(moment.timestamp()), "variabel": variable, "value": value}
                    for moment in times
                    for variable, value in ((1, 2.0), (2, 0.5), (3, 0.5), (4, 0.05))
                ])
            # Include forecasts before the gap and at the exclusive end bound.
            # Neither may replace recorded data or extend the report interval.
            connection.execute(forecasts.insert(), [
                {"time": int((start + dt.timedelta(hours=hour)).timestamp()),
                 "variabel": variable, "value": value}
                for hour in range(3)
                for variable, value in ((1, 9.0), (2, 1.0))
            ])
        event.listen(manager.engine, "before_cursor_execute", record_query)
        result = report.get_grid_data("", _vanaf=start, _tot=end, _interval="uur", _source=source)

        expect_forecast = source in ("all", "da") and not complete
        assert result["datasoort"].tolist() == (["recorded", "expected"] if expect_forecast else ["recorded"] * recorded_hours)
        assert result["consumption"].tolist() == ([2.0, 9.0] if expect_forecast else [2.0] * recorded_hours)
        assert result["production"].tolist() == ([0.5, 1.0] if expect_forecast else [0.5] * recorded_hours)
        assert pd.to_datetime(result["vanaf"]).tolist() == ([start, start + dt.timedelta(hours=1)] if expect_forecast else times)
        assert (result["tot"] <= end).all()
        forecast_queries = [query for query in queries if "FROM prognoses AS p1" in query]
        assert bool(forecast_queries) is expect_forecast
        if source == "da":
            report.get_sensor_data.assert_not_called()
    finally:
        manager.engine.dispose()
