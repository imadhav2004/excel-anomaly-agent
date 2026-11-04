import numpy as np
import pandas as pd

from anomaly_agent.detector import (
    calc_pct_change,
    detect_anomalies,
    get_severity,
)


def make_df(revenue, orders=None):
    n = len(revenue)
    return pd.DataFrame(
        {
            "Month": pd.date_range("2025-01-01", periods=n, freq="MS"),
            "Revenue": revenue,
            "Orders": orders if orders is not None else [50, 51, 49, 50, 50, 50][:n],
        }
    )


def test_big_jump_is_flagged():
    result = detect_anomalies(make_df([100, 102, 98, 101, 99, 150]))
    assert [a["metric"] for a in result] == ["Revenue"]
    assert result[0]["direction"] == "up"


def test_big_drop_is_flagged():
    result = detect_anomalies(make_df([100, 102, 98, 101, 99, 40]))
    assert result[0]["direction"] == "down"


def test_normal_data_is_not_flagged():
    assert detect_anomalies(make_df([100, 102, 98, 101, 99, 101])) == []


def test_jump_from_zero_is_flagged():
    result = detect_anomalies(make_df([100, 102, 98, 101, 99, 101], orders=[0, 0, 0, 0, 0, 50]))
    assert [a["metric"] for a in result] == ["Orders"]
    assert result[0]["pct_change"] is None


def test_zero_staying_zero_is_not_flagged():
    result = detect_anomalies(make_df([100, 102, 98, 101, 99, 101], orders=[0, 0, 0, 0, 0, 0]))
    assert result == []


def test_missing_latest_value_is_skipped():
    result = detect_anomalies(make_df([100, 102, 98, 101, 99, np.nan]))
    assert result == []


def test_too_little_history_is_skipped():
    df = make_df([100, 102, 150], orders=[50, 50, 50])
    assert detect_anomalies(df) == []


def test_flat_history_is_not_flagged():
    df = make_df([100, 100, 100, 100, 100, 100])
    assert detect_anomalies(df) == []


def test_pct_change_with_zero_previous_is_none():
    assert calc_pct_change(0, 50) is None
    assert calc_pct_change(100, 150) == 0.5


def test_severity_levels():
    assert get_severity(0.60, 0.5) == "HIGH"
    assert get_severity(0.10, 3.2) == "HIGH"
    assert get_severity(0.35, 1.0) == "MEDIUM"
    assert get_severity(0.10, 2.1) == "MEDIUM"
    assert get_severity(0.05, 0.5) == "LOW"
