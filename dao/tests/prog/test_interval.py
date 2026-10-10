"""
Tests voor de kwartier-resolutie in de rapportage/api.

Deze tests raken de database niet: ze controleren de hulpfuncties die bepalen
met welke stapgrootte de legacy-api ("/api/report/<veld>/<periode>") zijn
gegevens teruggeeft als de optimalisering met interval "15min" draait.
"""

import datetime
import sys

import pandas as pd

sys.path.append("../../../dao/prog")
from dao.prog.da_report import INTRADAY_INTERVALS, Report, interval_delta


def test_interval_delta():
    assert interval_delta("kwartier") == datetime.timedelta(minutes=15)
    assert interval_delta("uur") == datetime.timedelta(hours=1)
    # dag en maand worden per uur opgehaald
    assert interval_delta("dag") == datetime.timedelta(hours=1)
    assert interval_delta("maand") == datetime.timedelta(hours=1)


def test_intraday_intervals():
    assert "uur" in INTRADAY_INTERVALS
    assert "kwartier" in INTRADAY_INTERVALS


def test_generate_df_kwartier():
    vanaf = datetime.datetime(2025, 4, 6)
    tot = vanaf + datetime.timedelta(days=1)
    result = Report.generate_df(vanaf, tot, "kwartier")
    assert len(result) == 96
    assert result["tijd"].iloc[1] - result["tijd"].iloc[0] == datetime.timedelta(
        minutes=15
    )
    assert result["tijd"].iloc[-1] == tot - datetime.timedelta(minutes=15)


def test_generate_df_uur_ongewijzigd():
    vanaf = datetime.datetime(2025, 4, 6)
    tot = vanaf + datetime.timedelta(days=1)
    result = Report.generate_df(vanaf, tot, "uur")
    assert len(result) == 24


def test_generate_df_dag_met_kwartierstappen():
    """Een dag-rapport dat per kwartier wordt opgehaald houdt dag-labels."""
    vanaf = datetime.datetime(2025, 4, 6)
    tot = vanaf + datetime.timedelta(days=2)
    result = Report.generate_df(vanaf, tot, "dag", "kwartier")
    assert len(result) == 192
    assert set(result["dag"]) == {"2025-04-06", "2025-04-07"}


def test_spread_over_quarters_verdeelt_hoeveelheid():
    tijden = [
        datetime.datetime(2025, 4, 6, 9),
        datetime.datetime(2025, 4, 6, 10),
    ]
    df = pd.DataFrame({"tijd": tijden, "tot": tijden, "cons": [2.0, 4.0]})
    df.index = pd.to_datetime(df["tijd"])
    result = Report.spread_over_quarters(df, ["cons"])
    assert len(result) == 8
    assert list(result["cons"]) == [0.5] * 4 + [1.0] * 4
    # het totaal blijft gelijk
    assert result["cons"].sum() == df["cons"].sum()
    assert result["tijd"].iloc[1] == datetime.datetime(2025, 4, 6, 9, 15)


def test_spread_over_quarters_neemt_tarief_over():
    tijden = [datetime.datetime(2025, 4, 6, 9), datetime.datetime(2025, 4, 6, 10)]
    df = pd.DataFrame({"time": tijden, "da_cons": [0.25, 0.30]})
    df.index = pd.to_datetime(df["time"])
    result = Report.spread_over_quarters(
        df, ["da_cons"], quantity=False, time_column="time"
    )
    assert list(result["da_cons"]) == [0.25] * 4 + [0.30] * 4


def test_spread_over_quarters_laat_kwartierdata_ongemoeid():
    tijden = [
        datetime.datetime(2025, 4, 6, 9) + datetime.timedelta(minutes=15 * i)
        for i in range(4)
    ]
    df = pd.DataFrame({"tijd": tijden, "cons": [0.5, 0.5, 0.5, 0.5]})
    df.index = pd.to_datetime(df["tijd"])
    result = Report.spread_over_quarters(df, ["cons"])
    assert len(result) == 4
    assert list(result["cons"]) == [0.5] * 4


def test_recalc_df_ha_behoudt_kwartieren():
    """Kwartierprognoses mogen niet tot uurwaarden worden samengevoegd."""
    tijden = [
        datetime.datetime(2025, 4, 6, 9) + datetime.timedelta(minutes=15 * i)
        for i in range(4)
    ]
    df = pd.DataFrame(
        {
            "tijd": tijden,
            "consumption": [0.5] * 4,
            "production": [0.2] * 4,
            "da_cons": [0.30] * 4,
            "da_prod": [0.10] * 4,
            "datasoort": ["expected"] * 4,
        }
    )
    per_kwartier = Report.recalc_df_ha(None, df, "kwartier")
    assert len(per_kwartier) == 4
    assert per_kwartier["consumption"].sum() == 2.0

    per_uur = Report.recalc_df_ha(None, df, "uur")
    assert len(per_uur) == 1
    assert per_uur["consumption"].iloc[0] == 2.0
