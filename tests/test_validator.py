import pandas as pd
import pytest

from anomaly_agent.validator import DataError, check_data, check_file


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(DataError):
        check_file(tmp_path / "nope.xlsx")


def test_wrong_extension_is_rejected(tmp_path):
    file = tmp_path / "data.txt"
    file.write_text("hello")
    with pytest.raises(DataError):
        check_file(file)


def test_too_few_rows_is_rejected():
    df = pd.DataFrame({"Month": pd.date_range("2025-01-01", periods=3, freq="MS"), "Revenue": [1, 2, 3]})
    with pytest.raises(DataError):
        check_data(df, "Month")


def test_no_numeric_columns_is_rejected():
    df = pd.DataFrame(
        {"Month": pd.date_range("2025-01-01", periods=5, freq="MS"), "Region": list("abcde")}
    )
    with pytest.raises(DataError):
        check_data(df, "Month")
