import numpy as np
import pandas as pd

from anomaly_agent.data.cleaner import clean_data, coerce_numeric_columns, fill_gaps, suggest_fixes
from anomaly_agent.data.profiler import profile_data


def raw():
    return pd.DataFrame(
        {
            "Month": ["2025-01-01", "2025-02-01", "2025-02-01", None, "2025-03-01"],
            "Revenue": ["100", "200", "200", None, "n/a"],
        }
    )


def test_removes_empty_rows_and_duplicates():
    df, log = clean_data(raw(), "Month")
    assert len(df) == 3
    assert any("empty" in line for line in log)
    assert any("duplicate" in line for line in log)


def test_duplicates_can_be_kept():
    df, _ = clean_data(raw(), "Month", remove_duplicates=False)
    assert len(df) == 4  # only the empty row is removed


def test_text_numbers_become_numbers_and_bad_ones_become_empty():
    df, log = clean_data(raw(), "Month")
    assert pd.api.types.is_numeric_dtype(df["Revenue"])
    assert df["Revenue"].isna().sum() == 1
    assert any("became empty" in line for line in log)


def test_text_columns_stay_text():
    df = pd.DataFrame({"Region": ["a", "b", "c"], "Sales": [1, 2, 3]})
    out, notes = coerce_numeric_columns(df)
    assert out["Region"].tolist() == ["a", "b", "c"]
    assert notes == []


def test_the_original_table_is_not_changed():
    original = raw()
    clean_data(original, "Month")
    assert len(original) == 5


def test_fill_gaps_fills_the_middle_but_never_the_newest_value():
    df = pd.DataFrame({"Month": pd.date_range("2025-01-01", periods=5, freq="MS"),
                       "Revenue": [100.0, np.nan, 300.0, 400.0, np.nan]})
    out, filled = fill_gaps(df, "Month")
    assert out["Revenue"].tolist()[:4] == [100.0, 200.0, 300.0, 400.0]
    assert np.isnan(out["Revenue"].iloc[-1])  # the latest value stays empty
    assert filled == 1


def test_suggestions_mention_the_problems():
    df = pd.DataFrame(
        {"Month": ["2025-01-01", "2025-01-01", None],
         "Revenue": ["1", "1", "n/a"], "Notes": [None, None, None]}
    )
    text = " ".join(suggest_fixes(profile_data(df)))
    assert "duplicate" in text
    assert "not numbers" in text
    assert "empty" in text


def test_no_date_column_is_suggested_clearly():
    df = pd.DataFrame({"A": [1, 2, 3, 4], "B": [1, 2, 3, 4]})
    assert any("No date column" in tip for tip in suggest_fixes(profile_data(df)))
