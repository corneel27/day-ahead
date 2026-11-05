"""Predicted day-ahead prices appended by Report.get_price_data."""

import datetime as dt

import pandas as pd
import pytest

from dao.prog.da_report import Report

KNOWN_START = dt.datetime(2026, 10, 26, 22)
PREDICTION_START = dt.datetime(2026, 10, 27)


def _column_frame(moments: list[dt.datetime], values: list[float]) -> pd.DataFrame:
    """A frame shaped like DBmanagerObj.get_column_data without aggregation."""
    return pd.DataFrame(
        {
            "uur": [moment.strftime("%Y-%m-%d %H:00") for moment in moments],
            "time": [moment.strftime("%Y-%m-%d %H:%M") for moment in moments],
            "utc": [int(moment.timestamp()) for moment in moments],
            "value": values,
            "datasoort": "expected",
        }
    )


class _FakeDb:
    def __init__(self, known: pd.DataFrame, predicted: pd.DataFrame):
        self.frames = {"values": known, "prognoses": predicted}

    def get_column_data(self, tablename, column_name, start=None, end=None, agg_func=None):
        df = self.frames[tablename]
        moments = pd.to_datetime(df["time"])
        mask = moments >= start
        if end is not None:
            mask &= moments < end
        return df[mask].reset_index(drop=True)


def _report(predicted_step_minutes: int) -> Report:
    known = [KNOWN_START + dt.timedelta(minutes=15 * i) for i in range(8)]
    count = 8 * 60 // predicted_step_minutes
    predicted = [
        PREDICTION_START + dt.timedelta(minutes=predicted_step_minutes * i) for i in range(count)
    ]
    report = Report.__new__(Report)
    report.db_da = _FakeDb(
        _column_frame(known, [0.10] * len(known)),
        _column_frame(predicted, [0.20 + 0.001 * i for i in range(count)]),
    )
    for name in (
        "ol_l_def", "ol_t_def", "taxes_l_def", "taxes_t_def", "btw_l_def", "btw_t_def",
    ):
        setattr(report, name, {"2026-01-01": 0})
    report.multiplier_l_def = {"2026-01-01": 1}
    report.multiplier_t_def = {"2026-01-01": 1}
    report.prices_options = None
    return report


@pytest.mark.parametrize("predicted_step_minutes", [15, 60])
def test_predicted_quarters_have_one_row_each(predicted_step_minutes):
    report = _report(predicted_step_minutes)

    df = report.get_price_data(KNOWN_START, PREDICTION_START, "15min", extension=8)

    expected = [KNOWN_START + dt.timedelta(minutes=15 * i) for i in range(8 + 8 * 4)]
    assert df["time"].tolist() == expected


def test_quarter_predictions_keep_their_values():
    report = _report(15)

    df = report.get_price_data(KNOWN_START, PREDICTION_START, "15min", extension=8)

    predicted = df[df["time"] >= PREDICTION_START]
    assert predicted["da_ex"].tolist() == pytest.approx([0.20 + 0.001 * i for i in range(32)])


def test_hourly_predictions_average_to_the_hourly_value():
    report = _report(60)

    df = report.get_price_data(KNOWN_START, PREDICTION_START, "15min", extension=8)

    predicted = df[df["time"] >= PREDICTION_START].reset_index(drop=True)
    hourly_means = predicted.groupby(predicted.index // 4)["da_ex"].mean()
    assert hourly_means.tolist() == pytest.approx([0.20 + 0.001 * i for i in range(8)])
