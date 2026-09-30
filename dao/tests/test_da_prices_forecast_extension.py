import datetime
import importlib.util
import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd


# Keep this focused unit test runnable without installing DAO's database/providers.
if importlib.util.find_spec("sqlalchemy") is None:
    db_manager = types.ModuleType("dao.lib.db_manager")
    db_manager.DBmanagerObj = object
    sys.modules["dao.lib.db_manager"] = db_manager

if importlib.util.find_spec("entsoe") is None:
    entsoe = types.ModuleType("entsoe")
    entsoe.EntsoePandasClient = object
    sys.modules["entsoe"] = entsoe

if importlib.util.find_spec("nordpool") is None:
    nordpool = types.ModuleType("nordpool")
    elspot = types.ModuleType("nordpool.elspot")
    elspot.Prices = object
    nordpool.elspot = elspot
    sys.modules["nordpool"] = nordpool
    sys.modules["nordpool.elspot"] = elspot

from dao.lib.da_prices import DaPrices


class FakeDatabase:
    def __init__(self):
        self.deleted = []
        self.saved = []
        self.ensured = []
        self.official_horizon = datetime.datetime.now() + datetime.timedelta(hours=24)

    def ensure_variabel_record(self, **kwargs):
        self.ensured.append(kwargs)

    def delete_code_range(self, code, start=None, end=None):
        self.deleted.append((code, start, end))

    def get_time_border_record(self, code):
        return self.official_horizon

    def savedata(self, frame):
        self.saved.append(frame.copy())


def build_prices(country="NL", interval="1hour", **overrides):
    price_config = {
        "source_day_ahead": "tibber",
        "forecast_extension_provider": "energypriceforecast",
        "forecast_extension_hours": 24,
        "energypriceforecast_extension_api_url": "https://example.test/prices?source=dao",
        "energypriceforecast_extension_api_key": None,
        "energypriceforecast_extension_country": None,
    }
    price_config.update(overrides)
    config = SimpleNamespace(
        interval=interval,
        prices=SimpleNamespace(**price_config),
    )
    return DaPrices(config, FakeDatabase(), country=country)


class EnergyPriceForecastExtensionTest(unittest.TestCase):
    def test_request_forces_euro_and_preserves_existing_query(self):
        prices = build_prices(interval="15min")
        response = Mock()
        response.text = json.dumps(
            {
                "format": "dao-prices",
                "currency": "EUR",
                "entries": [
                    {
                        "start": "2026-09-09T08:00:00Z",
                        "end": "2026-09-09T09:00:00Z",
                        "value": 0.15,
                    }
                ],
                "meta": {
                    "used_horizon_hours": 48,
                    "allowed_horizon_hours": 48,
                },
            }
        )
        response.raise_for_status.return_value = None

        with patch("dao.lib.da_prices.get", return_value=response) as request:
            frame = prices._build_energypriceforecast_df(
                start=datetime.datetime(2026, 9, 9, 8),
                end=datetime.datetime(2026, 9, 10, 8),
                api_url="https://example.test/prices?source=dao",
                country="dk1",
                code="da_ext",
                forecast_only=True,
                hours_override=48,
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(len(frame), 4)
        self.assertEqual(frame["value"].tolist(), [0.15] * 4)
        self.assertEqual(frame.attrs["api_meta"]["used_horizon_hours"], 48)
        request.assert_called_once_with(
            "https://example.test/prices?source=dao",
            params={
                "country": "dk1",
                "hours": 48,
                "currency": "EUR",
                "mode": "forecast_only",
            },
            timeout=15,
            headers={"Authorization": "Bearer token"},
        )

    def test_non_euro_response_is_rejected(self):
        prices = build_prices(country="DK1")
        response = Mock()
        response.text = json.dumps({"currency": "DKK", "entries": []})
        response.raise_for_status.return_value = None

        with patch("dao.lib.da_prices.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "DAO verwacht EUR/kWh"):
                prices._build_energypriceforecast_df(
                    start=datetime.datetime(2026, 9, 9, 8),
                    end=datetime.datetime(2026, 9, 10, 8),
                    api_url="https://example.test/prices",
                    country="dk1",
                    code="da_ext",
                )

    def test_market_mapping_never_falls_back_to_netherlands(self):
        self.assertEqual(build_prices(country="FI")._resolve_market_country(None), "fi")
        self.assertEqual(build_prices(country="PL")._resolve_market_country(None), "pl")
        self.assertEqual(build_prices(country="CH")._resolve_market_country(None), "ch")
        self.assertIsNone(build_prices(country="DK")._resolve_market_country(None))
        self.assertIsNone(build_prices(country="GB")._resolve_market_country(None))
        self.assertEqual(build_prices(country="SE")._resolve_market_country("se4"), "se4")
        self.assertIsNone(build_prices(country="NL")._resolve_market_country("invalid"))

    def test_empty_refresh_keeps_existing_extension_values(self):
        prices = build_prices(country="NL")
        empty = pd.DataFrame(columns=["time", "code", "value"])

        with patch.object(prices, "_build_energypriceforecast_df", return_value=empty):
            prices.get_price_forecast_extension()

        self.assertEqual(prices.db_da.deleted, [])
        self.assertEqual(prices.db_da.saved, [])

    def test_extension_hours_are_measured_from_returned_horizon(self):
        frame = pd.DataFrame(
            [
                ["1000", "da_ext", 0.1],
                ["1900", "da_ext", 0.2],
                ["2800", "da_ext", 0.3],
                ["3700", "da_ext", 0.4],
            ],
            columns=["time", "code", "value"],
        )
        self.assertEqual(
            DaPrices._extension_horizon_hours(frame, 1000, resolution_seconds=900),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
