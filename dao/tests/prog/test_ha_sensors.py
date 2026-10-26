"""
Tests voor het schrijven van rapportage-data naar HA-entiteiten (report: ha_sensors).

Deze tests raken de database en Home Assistant niet: get_api_df, de database
en set_state worden vervangen.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dao.prog.config.models.report import ReportConfig
from dao.prog.da_report import Report


def make_report(include: bool, extension: int, entities: dict) -> Report:
    report = object.__new__(Report)
    report.report_options = ReportConfig.model_validate(
        {"ha_sensors": {"include_price_prediction": include, **entities}}
    )
    today = datetime.datetime.combine(datetime.date.today(), datetime.time())
    report.periodes = {
        "vandaag en morgen": {
            "vanaf": today,
            "tot": today + datetime.timedelta(days=2),
            "interval": "uur",
        }
    }
    report.interval_s = 3600
    report.config = SimpleNamespace(
        prices=SimpleNamespace(prediction=SimpleNamespace(extension=extension))
    )
    report.set_state = MagicMock()
    return report


def column_df(start: datetime.datetime, hours: int) -> pd.DataFrame:
    utc = [int((start + datetime.timedelta(hours=h)).timestamp()) for h in range(hours)]
    return pd.DataFrame({"utc": utc})


def api_df(start: datetime.datetime, hours: int, **columns) -> pd.DataFrame:
    times = [start + datetime.timedelta(hours=h) for h in range(hours)]
    df = pd.DataFrame(
        {
            "time_ts": [t.timestamp() * 1000 for t in times],
            "time": [t.strftime("%Y-%m-%d %H:%M") for t in times],
        }
    )
    for name, values in columns.items():
        df[name] = values
    df["datatype"] = "expected"
    return df


def test_config_defaults():
    config = ReportConfig.model_validate({})
    assert config.ha_sensors.include_price_prediction is False
    assert config.ha_sensors.da_cons is None


def test_config_invalid_entity():
    with pytest.raises(ValueError):
        ReportConfig.model_validate(
            {"ha_sensors": {"da_cons": "geen entity"}}
        )


def test_config_invalid_soc_battery_entity():
    with pytest.raises(ValueError):
        ReportConfig.model_validate({"ha_sensors": {"soc_0": "geen entity"}})


def test_config_duplicate_entity():
    with pytest.raises(ValueError, match="sensor.dao_price"):
        ReportConfig.model_validate(
            {"ha_sensors": {"da_cons": "sensor.dao_price", "da_prod": "sensor.dao_price"}}
        )


def test_price_prediction_range():
    report = make_report(True, 24, {})
    today = report.periodes["vandaag en morgen"]["vanaf"]
    end_known = today + datetime.timedelta(days=1)
    report.db_da = MagicMock()
    # bekende prijzen tot het einde van vandaag, voorspelde prijzen 10 uur verder
    report.db_da.get_column_data.side_effect = [
        column_df(today, 24),
        column_df(end_known, 10),
    ]
    assert report.get_price_prediction_range(today) == (
        end_known,
        end_known + datetime.timedelta(hours=10),
    )


def test_price_prediction_range_without_extension():
    report = make_report(True, 0, {})
    today = report.periodes["vandaag en morgen"]["vanaf"]
    report.db_da = MagicMock()
    report.db_da.get_column_data.return_value = column_df(today, 24)
    end_known = today + datetime.timedelta(days=1)
    assert report.get_price_prediction_range(today) == (end_known, end_known)


def test_current_row():
    start = datetime.datetime(2026, 10, 20)
    df = api_df(start, 4, value=[1.0, 2.0, 3.0, 4.0])
    row = Report.current_row(df, start + datetime.timedelta(hours=2, minutes=30))
    assert row["value"] == 3.0
    assert Report.current_row(df, start - datetime.timedelta(minutes=1)) is None


def test_ha_sensor_entities():
    report = make_report(False, 0, {
        "da_prod": "sensor.dao_price_production",
        "bat_in": "sensor.dao_battery_in",
        "soc_1": "sensor.dao_soc_accu_2",
    })
    assert report.ha_sensor_entities(report.report_options.ha_sensors) == {
        "da_prod": ("sensor.dao_price_production", "da", "da_prod"),
        "bat_in": ("sensor.dao_battery_in", "bat_in", "value"),
        "soc_1": ("sensor.dao_soc_accu_2", "soc_1", "value"),
    }


@pytest.mark.parametrize("include, tot_hours, extension", [(False, 24, 0), (True, 54, 30)])
def test_push_ha_sensors_prediction_range(include, tot_hours, extension):
    entities = {
        "da_ex": "sensor.dao_spot_price",
        "da_cons": "sensor.dao_price_consumption",
        "bat_in": "sensor.dao_battery_in",
    }
    report = make_report(include, 48, entities)
    today = report.periodes["vandaag en morgen"]["vanaf"]
    end_known = today + datetime.timedelta(days=1)
    # de voorspelde prijzen lopen tot na morgen
    report.get_price_prediction_range = MagicMock(
        return_value=(end_known, end_known + datetime.timedelta(hours=30))
    )
    hours = tot_hours
    report.get_api_df = MagicMock(
        side_effect=[
            api_df(today, hours, da_ex=[0.1] * hours, da_cons=[0.25] * hours,
                   da_prod=[0.2] * hours),
            api_df(today, hours, value=[1.5] * hours),
        ]
    )

    assert report.push_ha_sensors() is True

    # de prijzen worden een keer opgehaald voor beide prijs-sensoren
    assert [call.args[0] for call in report.get_api_df.call_args_list] == ["da", "bat_in"]
    for call in report.get_api_df.call_args_list:
        assert call.kwargs["_tot"] == today + datetime.timedelta(hours=tot_hours)
        assert call.kwargs["extension"] == extension
    spot, prices, battery = report.set_state.call_args_list
    assert spot.args == ("sensor.dao_spot_price", 0.1)
    assert prices.args == ("sensor.dao_price_consumption", 0.25)
    assert prices.kwargs["attributes"]["unit_of_measurement"] == "EUR/kWh"
    data = prices.kwargs["attributes"]["data"]
    assert len(data) == hours
    assert set(data[0]) == {"time_ts", "time", "value", "datatype"}
    assert data[0]["value"] == 0.25
    assert battery.args == ("sensor.dao_battery_in", 1.5)
    assert battery.kwargs["attributes"]["friendly_name"] == "DAO bat_in"
    # alle entiteiten van een push hebben dezelfde last_update
    assert (
        battery.kwargs["attributes"]["last_update"]
        == prices.kwargs["attributes"]["last_update"]
    )
    assert battery.kwargs["attributes"]["unit_of_measurement"] == "kW"


def test_push_ha_sensors_error_does_not_stop_others():
    report = make_report(False, 0, {
        "soc": "sensor.dao_soc",
        "cons": "sensor.dao_cons",
    })
    today = report.periodes["vandaag en morgen"]["vanaf"]
    report.get_price_prediction_range = MagicMock(return_value=(None, None))
    report.get_api_df = MagicMock(
        side_effect=[
            '{"message":"Failed", "reason": "..."}',
            api_df(today, 48, value=[50.0] * 48),
        ]
    )
    # cons faalt, soc wordt toch geschreven
    assert report.push_ha_sensors() is False
    assert report.set_state.call_count == 1
    assert report.set_state.call_args.args == ("sensor.dao_soc", 50.0)
    assert report.set_state.call_args.kwargs["attributes"]["unit_of_measurement"] == "%"


def test_push_ha_sensors_none_configured():
    report = make_report(False, 0, {})
    report.get_api_df = MagicMock()
    assert report.push_ha_sensors() is True
    report.get_api_df.assert_not_called()
