"""
Tests for the weather data the ML solar prediction is fed.

The report page compares the DAO prediction and the ML prediction for one day.
The DAO prediction takes, per hour, the measured irradiance when it is present
and the forecast otherwise. The ML prediction used the forecast unconditionally,
so for a day in the past the two columns were computed from different irradiance
series and their R2 was not comparable. ``prefer_measured`` makes the ML path
apply the same per hour choice.

Combining two series per hour only works when the values are keyed on their
timestamp, so these tests also cover the alignment of the weather items.
"""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

from dao.lib.db_manager import DBmanagerObj
from dao.prog.solar_predictor import SolarPredictor

# de codes zoals check_db.py ze aanmaakt
VARIABELEN = {"gr": 4, "temp": 5, "winds": 23}

DAY = dt.datetime(2026, 9, 1)


def _values_table(name: str, metadata: MetaData) -> Table:
    return Table(
        name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(
            "variabel",
            Integer,
            ForeignKey("variabel.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("time", BigInteger, nullable=False),
        Column("value", Float),
        UniqueConstraint("variabel", "time"),
    )


@pytest.fixture
def db_da(tmp_path):
    """A DBmanagerObj on an empty sqlite day ahead database."""
    db = DBmanagerObj(
        db_dialect="sqlite",
        db_name="day_ahead.db",
        db_path=str(tmp_path),
    )
    metadata = MetaData()
    variabel = Table(
        "variabel",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("code", String(10), unique=True, nullable=False),
        Column("name", String(50), unique=True, nullable=False),
        Column("dim", String(10), nullable=False),
    )
    _values_table("values", metadata)
    _values_table("prognoses", metadata)
    metadata.create_all(db.engine)
    with db.engine.connect() as connection:
        for code, variabel_id in VARIABELEN.items():
            connection.execute(
                variabel.insert().values(
                    id=variabel_id, code=code, name=code, dim="x"
                )
            )
        connection.commit()
    return db


@pytest.fixture
def predictor(db_da):
    """A SolarPredictor with only the day ahead database wired up.

    ``__init__`` needs a configuration and a Home Assistant connection, which
    ``get_weatherdata`` itself does not touch.
    """
    instance = object.__new__(SolarPredictor)
    instance.db_da = db_da
    return instance


def _save(db, table: str, code: str, values_per_hour: dict):
    """Slaat waarden op, met het uur van de dag als sleutel."""
    table_obj = db.get_table(table)
    with db.engine.connect() as connection:
        for hour, value in values_per_hour.items():
            connection.execute(
                table_obj.insert().values(
                    variabel=VARIABELEN[code],
                    time=int((DAY + dt.timedelta(hours=hour)).timestamp()),
                    value=value,
                )
            )
        connection.commit()


def _full_day(offset: float) -> dict:
    return {hour: offset + hour for hour in range(24)}


def _at(frame, hour: int, column: str):
    """De waarde van een kolom op een uur van DAY."""
    moment = (DAY + dt.timedelta(hours=hour)).astimezone(dt.timezone.utc)
    return frame.loc[moment, column]


def test_prefers_measured_irradiance_per_hour(predictor, db_da):
    """Per hour the measurement when present, the forecast otherwise."""
    for code, offset in (("gr", 1000.0), ("temp", 100.0), ("winds", 10.0)):
        _save(db_da, "prognoses", code, _full_day(offset))
        # measurements exist for the first half of the day only
        _save(db_da, "values", code, {hour: offset * 2 + hour for hour in range(12)})

    weather = predictor.get_weatherdata(
        DAY, DAY + dt.timedelta(days=1), prognose=True, prefer_measured=True
    )

    assert len(weather) == 24
    # measured hours
    assert _at(weather, 0, "irradiance") == 2000.0
    assert _at(weather, 11, "irradiance") == 2011.0
    assert _at(weather, 11, "temperature") == 211.0
    assert _at(weather, 11, "windvelocity") == 31.0
    # forecast hours
    assert _at(weather, 12, "irradiance") == 1012.0
    assert _at(weather, 23, "irradiance") == 1023.0


def test_default_still_uses_only_the_forecast(predictor, db_da):
    """The optimisation keeps reading the forecast, measurements or not."""
    _save(db_da, "prognoses", "gr", _full_day(1000.0))
    _save(db_da, "values", "gr", _full_day(2000.0))

    weather = predictor.get_weatherdata(
        DAY, DAY + dt.timedelta(days=1), prognose=True
    )

    assert _at(weather, 0, "irradiance") == 1000.0
    assert _at(weather, 23, "irradiance") == 1023.0


def test_prefer_measured_without_measurements_uses_the_forecast(predictor, db_da):
    """A day in the future has no measurements, so nothing changes there."""
    _save(db_da, "prognoses", "gr", _full_day(1000.0))

    weather = predictor.get_weatherdata(
        DAY, DAY + dt.timedelta(days=1), prognose=True, prefer_measured=True
    )

    assert len(weather) == 24
    assert _at(weather, 0, "irradiance") == 1000.0
    assert _at(weather, 23, "irradiance") == 1023.0


def test_weather_items_stay_on_their_own_hour(predictor, db_da):
    """A gap in one item may not shift the other items onto wrong hours."""
    _save(db_da, "prognoses", "gr", _full_day(1000.0))
    _save(db_da, "prognoses", "winds", _full_day(10.0))
    incomplete = _full_day(100.0)
    del incomplete[5]
    _save(db_da, "prognoses", "temp", incomplete)

    weather = predictor.get_weatherdata(
        DAY, DAY + dt.timedelta(days=1), prognose=True
    )

    assert len(weather) == 24
    assert _at(weather, 4, "temperature") == 104.0
    assert pd.isna(_at(weather, 5, "temperature"))
    # the hours after the gap keep their own value instead of shifting up
    assert _at(weather, 6, "temperature") == 106.0
    assert _at(weather, 23, "temperature") == 123.0
    assert _at(weather, 23, "irradiance") == 1023.0


def test_reads_measurements_for_training(predictor, db_da, monkeypatch):
    """Training reads the KNMI measurements, not the forecast."""
    monkeypatch.setattr(predictor, "import_knmi_df", lambda *a, **k: None)
    _save(db_da, "prognoses", "gr", _full_day(1000.0))
    for code, offset in (("gr", 2000.0), ("temp", 100.0), ("winds", 10.0)):
        _save(db_da, "values", code, _full_day(offset))

    weather = predictor.get_weatherdata(DAY)

    assert _at(weather, 0, "irradiance") == 2000.0
    assert _at(weather, 23, "irradiance") == 2023.0

