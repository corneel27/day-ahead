"""copy_col_df and add_col_df with the repeated hour at the end of DST."""
import pandas as pd

from dao.prog.da_report import Report


def _frame(times, column, values):
    times = pd.to_datetime(times)
    return pd.DataFrame({"tijd": times, column: values}, index=times)


REPEATED = ["2026-10-25 01:00", "2026-10-25 02:00", "2026-10-25 02:00", "2026-10-25 03:00"]
SINGLE = ["2026-10-25 01:00", "2026-10-25 02:00", "2026-10-25 03:00"]


def test_copy_repeated_hour_row_by_row():
    prices = _frame(REPEATED, "da_cons", [1.0, 2.0, 3.0, 4.0])
    target = _frame(REPEATED, "consumption", [1.0] * 4)
    result = Report.copy_col_df(prices, target, "da_cons")
    assert list(result["da_cons"]) == [1.0, 2.0, 3.0, 4.0]


def test_copy_repeated_source_into_single_target():
    prices = _frame(REPEATED, "da_cons", [1.0, 2.0, 3.0, 4.0])
    target = _frame(SINGLE, "consumption", [1.0] * 3)
    result = Report.copy_col_df(prices, target, "da_cons")
    assert list(result["da_cons"]) == [1.0, 2.0, 4.0]


def test_copy_single_source_fills_both_repeated_rows():
    prices = _frame(SINGLE, "da_cons", [1.0, 2.0, 4.0])
    target = _frame(REPEATED, "consumption", [1.0] * 4)
    result = Report.copy_col_df(prices, target, "da_cons")
    assert list(result["da_cons"]) == [1.0, 2.0, 2.0, 4.0]


def test_copy_adds_missing_times_as_rows():
    prices = _frame(REPEATED, "da_cons", [1.0, 2.0, 3.0, 4.0])
    target = _frame(REPEATED[:1], "consumption", [1.0])
    result = Report.copy_col_df(prices, target, "da_cons")
    assert list(result["da_cons"]) == [1.0, 2.0, 3.0, 4.0]
    assert len(result) == 4


def test_copy_into_empty_frame():
    prices = _frame(SINGLE, "da_cons", [1.0, 2.0, 4.0])
    result = Report.copy_col_df(prices, pd.DataFrame(), "da_cons")
    assert list(result["da_cons"]) == [1.0, 2.0, 4.0]
    assert list(result.index) == list(pd.to_datetime(SINGLE))


def test_add_repeated_hour_row_by_row_and_skips_missing():
    source = _frame(REPEATED, "consumption", [1.0, 2.0, 3.0, 4.0])
    target = _frame(SINGLE, "consumption", [10.0, 10.0, 10.0])
    result = Report.add_col_df(source, target, "consumption")
    assert list(result["consumption"]) == [11.0, 12.0, 14.0]

    target = _frame(REPEATED, "consumption", [10.0] * 4)
    result = Report.add_col_df(source, target, "consumption", negation=True)
    assert list(result["consumption"]) == [9.0, 8.0, 7.0, 6.0]
