import pandas as pd
import pytest

from anomaly_agent.loader import load_data
from anomaly_agent.validator import DataError


def save(tmp_path, data):
    path = tmp_path / "sales.xlsx"
    pd.DataFrame(data).to_excel(path, index=False)
    return path


def good_data():
    return {
        "Month": ["2025-03-01", "2025-01-01", "2025-02-01", "2025-04-01", "2025-05-01"],
        "Revenue": [300, 100, 200, 400, 500],
    }


def test_rows_are_sorted_by_date(tmp_path):
    df = load_data(save(tmp_path, good_data()))
    assert list(df["Revenue"]) == [100, 200, 300, 400, 500]


def test_missing_date_column_is_rejected(tmp_path):
    with pytest.raises(DataError):
        load_data(save(tmp_path, good_data()), date_column="Date")


def test_text_in_number_column_becomes_empty_number(tmp_path):
    data = good_data()
    data["Revenue"] = [300, 100, "n/a", 400, 500]
    df = load_data(save(tmp_path, data))
    assert df["Revenue"].isna().sum() == 1


def test_invalid_date_row_is_dropped(tmp_path):
    data = good_data()
    data["Month"][2] = "not a date"
    data["Month"].append("2025-06-01")
    data["Revenue"].append(600)
    df = load_data(save(tmp_path, data))
    assert len(df) == 5


def test_csv_files_can_be_loaded(tmp_path):
    path = tmp_path / "sales.csv"
    pd.DataFrame(good_data()).to_csv(path, index=False)
    df = load_data(path)
    assert list(df["Revenue"]) == [100, 200, 300, 400, 500]


def test_a_chosen_sheet_is_loaded(tmp_path):
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Month": ["2025-01-01"], "Revenue": [1]}).to_excel(writer, sheet_name="Tiny", index=False)
        pd.DataFrame(good_data()).to_excel(writer, sheet_name="Full", index=False)
    assert len(load_data(path, sheet_name="Full")) == 5
    with pytest.raises(DataError):
        load_data(path, sheet_name="Tiny")  # one row is not enough
