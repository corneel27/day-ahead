"""KNMI request defaults must not leak mutations between calls."""

import datetime as dt

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
