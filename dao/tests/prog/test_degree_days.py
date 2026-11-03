"""
Tests for Meteo.calc_graaddagen with a configurable base temperature (stookgrens).

The method is pure when avg_temp is passed in, so no database is needed: the Meteo
instance is created without running __init__.
"""

import datetime

import pytest

# da_meteo needs the full application dependencies; skip where they are absent
pytest.importorskip("ephem")
pytest.importorskip("knmi")
pytest.importorskip("sqlalchemy")

from dao.lib.da_meteo import DEFAULT_DEGREE_DAYS_BASE_TEMP, Meteo  # noqa: E402


@pytest.fixture
def meteo():
    return Meteo.__new__(Meteo)


# 15 October: the weight factor of March and October is 1.0
OCTOBER = datetime.datetime(2026, 10, 15)
JANUARY = datetime.datetime(2026, 1, 15)
JULY = datetime.datetime(2026, 7, 15)


class TestCalcGraaddagen:

    def test_fallback_base_temperature_is_16(self):
        assert DEFAULT_DEGREE_DAYS_BASE_TEMP == 16.0

    def test_default_uses_16_degrees(self, meteo):
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=10.0) == pytest.approx(6.0)

    def test_no_degree_days_at_or_above_default_base(self, meteo):
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=16.0) == 0
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=17.0) == 0

    def test_higher_base_temperature_starts_heating_earlier(self, meteo):
        # 17 °C average: no demand with the default, one degree day with base 18
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=17.0) == 0
        assert meteo.calc_graaddagen(
            date=OCTOBER, avg_temp=17.0, base_temp=18.0
        ) == pytest.approx(1.0)

    def test_lower_base_temperature_stops_heating_earlier(self, meteo):
        # 15 °C average: one degree day with the default, none with base 14
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=15.0) == pytest.approx(1.0)
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=15.0, base_temp=14.0) == 0

    def test_no_degree_days_exactly_at_the_configured_base(self, meteo):
        assert meteo.calc_graaddagen(date=OCTOBER, avg_temp=18.0, base_temp=18.0) == 0

    def test_weighting_uses_the_configured_base_temperature(self, meteo):
        winter = meteo.calc_graaddagen(
            date=JANUARY, avg_temp=8.0, weighted=True, base_temp=18.0
        )
        summer = meteo.calc_graaddagen(
            date=JULY, avg_temp=8.0, weighted=True, base_temp=18.0
        )
        assert winter == pytest.approx(1.1 * 10.0)
        assert summer == pytest.approx(0.8 * 10.0)

    def test_weighted_default_is_unchanged(self, meteo):
        assert meteo.calc_graaddagen(
            date=JANUARY, avg_temp=6.0, weighted=True
        ) == pytest.approx(1.1 * 10.0)
