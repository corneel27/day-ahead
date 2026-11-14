"""Solar report columns with and without ML prediction."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from dao.prog.da_report import Report

DAY = dt.date(2026, 6, 1)
HOURS = pd.date_range(dt.datetime(2026, 6, 1), periods=24, freq="h")
SLOTS = [int(moment.timestamp()) for moment in HOURS]


def hourly(column: str, value: float) -> pd.DataFrame:
    frame = pd.DataFrame({"tijd": HOURS, "slot": SLOTS, column: [value] * 24})
    frame.index = frame["tijd"]
    return frame


def make_report(ml_prediction: bool, sensors: list[str]):
    report = Report.__new__(Report)
    report.get_da_data = Mock(side_effect=lambda *args: hourly("gr", 10.0))
    report.get_sensor_data = Mock(side_effect=lambda *args: hourly("gemeten", 0.5))
    report.calc_prod_solar = Mock(return_value=0.4)
    report.calc_solar_predictions = Mock(return_value=hourly("prediction", 0.3))
    device = SimpleNamespace(
        name="roof", ml_prediction=ml_prediction, entities_sensors=sensors
    )
    return report, device


@pytest.mark.parametrize("view", ["grafiek", "tabel"])
def test_solar_report_without_ml_fills_only_dao_columns(view):
    report, device = make_report(ml_prediction=False, sensors=["sensor.pv"])
    result = report.calc_solar_data(device, DAY, view)

    report.calc_solar_predictions.assert_not_called()
    if view == "tabel":
        hours = result.iloc[:24]
        assert (hours[("Productie", "prognose dao", "kWh")] == 0.4).all()
        assert (hours[("Productie", "gemeten", "kWh")] == 0.5).all()
        assert (hours[("Productie", "prognose ml", "kWh")] == "").all()
    else:
        assert (result["prognose_dao"] == 0.4).all()
        assert (result["gemeten_prod"] == 0.5).all()
        assert result["prognose_ml"].isna().all()


def test_solar_report_with_ml_fills_ml_column():
    report, device = make_report(ml_prediction=True, sensors=["sensor.pv"])
    result = report.calc_solar_data(device, DAY, "grafiek")

    report.calc_solar_predictions.assert_called_once()
    assert (result["prognose_ml"] == 0.3).all()
    assert (result["prognose_dao"] == 0.4).all()


def test_solar_report_without_production_sensors():
    report, device = make_report(ml_prediction=False, sensors=[])
    result = report.calc_solar_data(device, DAY, "grafiek")

    report.get_sensor_data.assert_not_called()
    assert result["gemeten_prod"].isna().all()
    assert (result["prognose_dao"] == 0.4).all()
