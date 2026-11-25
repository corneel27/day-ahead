"""KNMI request defaults must not leak mutations between calls."""

import datetime as dt
from unittest.mock import Mock

import pandas as pd

from dao.prog import solar_predictor


def test_knmi_default_variables_are_fresh_per_call(monkeypatch):
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    predictor.knmi_station = 260
    requested = []

    def fetch(stations, *, start, end, variables):
        requested.append(list(variables))
        variables.append("mutated-by-client")
        return pd.DataFrame()

    monkeypatch.setattr(solar_predictor.knmi, "get_hour_data_dataframe", fetch)
    start, end = dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 15)
    predictor.get_and_save_knmi_data(start, end)
    predictor.get_and_save_knmi_data(start, end)
    assert requested == [["FH", "T", "Q"], ["FH", "T", "Q"]]


def test_knmi_explicit_empty_variables_are_preserved(monkeypatch):
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    predictor.knmi_station = 260
    requested = []

    def fetch(stations, *, start, end, variables):
        requested.append(variables)
        return pd.DataFrame()

    monkeypatch.setattr(solar_predictor.knmi, "get_hour_data_dataframe", fetch)
    variables = []
    predictor.get_and_save_knmi_data(dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 15), variables)
    assert requested == [[]]
    assert requested[0] is variables


def test_knmi_wind_only_backfill_saves_wind(monkeypatch):
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    predictor.knmi_station = 260
    predictor.time_zone = "UTC"
    predictor.db_da = Mock()
    wind_data = pd.DataFrame({"FH": [25, 40]}, index=pd.date_range("2026-01-14", periods=2, freq="h"))
    fetch = Mock(return_value=wind_data)
    monkeypatch.setattr(solar_predictor.knmi, "get_hour_data_dataframe", fetch)
    start, end = dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 15)

    predictor.get_and_save_knmi_data(start, end, ["FH"])

    assert fetch.call_args.kwargs["variables"] == ["FH"]
    saved = predictor.db_da.savedata.call_args
    assert saved.kwargs["tablename"] == "values"
    assert saved.args[0]["code"].tolist() == ["winds", "winds"]
    assert saved.args[0]["value"].tolist() == [2.5, 4.0]


def test_initial_weather_import_populates_empty_database():
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    start, end = dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 15)
    predictor.db_da = Mock()
    predictor.db_da.get_time_border_record.side_effect = [None, None, None, None, start, end]
    predictor.get_and_save_meteo_data = Mock()
    predictor.save_meteo_history_source = Mock()

    predictor.import_meteo(start, end)

    predictor.get_and_save_meteo_data.assert_called_once_with(start, end)
    predictor.save_meteo_history_source.assert_called_once_with()


def test_initial_weather_import_handles_empty_response():
    predictor = solar_predictor.SolarPredictor.__new__(solar_predictor.SolarPredictor)
    predictor.db_da = Mock()
    predictor.db_da.get_time_border_record.return_value = None
    predictor.get_and_save_meteo_data = Mock()
    predictor.save_meteo_history_source = Mock()
    start, end = dt.datetime(2026, 1, 14), dt.datetime(2026, 1, 15)

    predictor.import_meteo(start, end)

    predictor.get_and_save_meteo_data.assert_called_once_with(start, end)
    predictor.save_meteo_history_source.assert_not_called()
