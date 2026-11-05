import pandas as pd

from anomaly_agent.data.profiler import find_date_column, profile_data


def sample():
    return pd.DataFrame(
        {
            "Region": ["North", "South", "East", "West", "North"],
            "Revenue": [100, 200, 300, 400, 500],
            "When": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-05-01"],
        }
    )


def test_finds_a_text_date_column_with_any_name():
    assert find_date_column(sample()) == "When"


def test_finds_a_real_date_column():
    df = sample()
    df["When"] = pd.to_datetime(df["When"])
    assert find_date_column(df) == "When"


def test_prefers_a_column_with_a_date_like_name():
    df = sample()
    df["Month"] = df["When"]
    assert find_date_column(df) == "Month"


def test_numbers_are_not_mistaken_for_dates():
    df = pd.DataFrame({"A": [1, 2, 3, 4], "B": [10, 20, 30, 40]})
    assert find_date_column(df) is None


def test_names_and_text_are_not_mistaken_for_dates():
    df = pd.DataFrame({"Region": ["North", "South", "East", "West"], "Sales": [1, 2, 3, 4]})
    assert find_date_column(df) is None


def test_profile_counts_problems():
    df = pd.DataFrame(
        {
            "Month": ["2025-01-01", "2025-02-01", "bad date", "2025-02-01", None],
            "Revenue": ["100", "200", "n/a", "200", None],
            "Notes": [None, None, None, None, None],
        }
    )
    profile = profile_data(df)
    assert profile["date_column"] == "Month"
    assert profile["rows"] == 5
    assert profile["empty_rows"] == 1
    assert profile["invalid_dates"] == 1
    assert profile["text_in_numeric"] == {"Revenue": 1}
    assert profile["column_types"]["Revenue"] == "number (stored as text)"
    assert "Notes" in profile["mostly_empty"]
    assert profile["missing_total"] > 0


def test_profile_counts_duplicates():
    df = pd.DataFrame({"Month": ["2025-01-01", "2025-01-01"], "Revenue": [1, 1]})
    assert profile_data(df)["duplicate_rows"] == 1
