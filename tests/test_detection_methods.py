import numpy as np
import pandas as pd
import pytest

from anomaly_agent.detection import iqr, isolation, pct_change, rolling, seasonal, zscore
from anomaly_agent.detection.base import (
    DetectionSettings,
    fmt,
    make_anomaly,
    severity_from_score,
)

SETTINGS = DetectionSettings()


def monthly(values, start="2025-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


CALM = [100, 102, 99, 101, 100, 103, 98, 101]


# ---------- shared helpers ----------
def test_severity_levels():
    assert severity_from_score(1.0) == "LOW"
    assert severity_from_score(1.5) == "MEDIUM"
    assert severity_from_score(2.0) == "HIGH"


def test_record_has_every_field_and_the_right_deviation():
    record = make_anomaly(pd.Timestamp("2025-01-01"), "Sales", "iqr", 150, 100, 2.5, "text")
    assert record["deviation_pct"] == pytest.approx(0.5)
    assert record["direction"] == "up"
    assert record["severity"] == "HIGH"
    for key in ("period", "metric", "method", "actual", "expected", "score", "explanation"):
        assert key in record


def test_deviation_is_none_when_expected_is_zero():
    assert make_anomaly(pd.Timestamp("2025-01-01"), "x", "m", 5, 0, 1, "t")["deviation_pct"] is None


def test_number_format():
    assert fmt(145000) == "145,000"
    assert fmt(2.456) == "2.46"


# ---------- percent change ----------
def test_pct_change_flags_a_jump_and_names_the_period():
    found, reason = pct_change.detect(monthly(CALM + [150]), "Sales", SETTINGS)
    assert reason is None
    assert len(found) == 1
    assert found[0]["period"] == pd.Timestamp("2025-09-01")
    assert found[0]["expected"] == 101  # the previous value
    assert found[0]["deviation_pct"] == pytest.approx(49 / 101)


def test_pct_change_flags_a_drop():
    found, _ = pct_change.detect(monthly(CALM + [60]), "Sales", SETTINGS)
    assert found[-1]["direction"] == "down"


def test_pct_change_ignores_calm_data():
    assert pct_change.detect(monthly(CALM), "Sales", SETTINGS)[0] == []


def test_pct_change_from_zero_is_flagged_without_a_percentage():
    found, _ = pct_change.detect(monthly([0, 0, 5]), "Sales", SETTINGS)
    assert len(found) == 1 and found[0]["deviation_pct"] is None


def test_pct_change_needs_two_values():
    assert pct_change.detect(monthly([5]), "Sales", SETTINGS)[1] is not None


def test_pct_change_skips_empty_cells():
    found, _ = pct_change.detect(monthly([100, np.nan, 100, 150]), "Sales", SETTINGS)
    assert len(found) == 1  # 100 -> 150, the empty cell is jumped over


# ---------- z-score ----------
def test_zscore_flags_a_spike():
    found, _ = zscore.detect(monthly(CALM + [160]), "Sales", SETTINGS)
    assert [f["period"] for f in found] == [pd.Timestamp("2025-09-01")]
    assert found[0]["score"] >= 1
    assert found[0]["direction"] == "up"


def test_zscore_skips_a_constant_series_with_a_reason():
    found, reason = zscore.detect(monthly([5, 5, 5, 5, 5]), "Sales", SETTINGS)
    assert found == [] and "same" in reason


def test_zscore_needs_enough_values():
    assert zscore.detect(monthly([1, 2, 3]), "Sales", SETTINGS)[1] is not None


# ---------- IQR ----------
def test_iqr_flags_high_and_low_outliers():
    found, _ = iqr.detect(monthly(CALM + [160, 20]), "Sales", SETTINGS)
    assert {f["direction"] for f in found} == {"up", "down"}
    assert all(f["actual"] in (160.0, 20.0) for f in found)


def test_iqr_ignores_calm_data():
    assert iqr.detect(monthly(CALM), "Sales", SETTINGS)[0] == []


def test_iqr_explains_with_a_normal_range():
    found, _ = iqr.detect(monthly(CALM + [160]), "Sales", SETTINGS)
    assert "normal range" in found[0]["explanation"]


def test_iqr_skips_when_the_middle_half_is_identical():
    values = [50, 50, 50, 50, 50, 50, 50, 95]
    assert iqr.detect(monthly(values), "Sales", SETTINGS)[1] is not None


# ---------- rolling window ----------
def test_rolling_flags_a_jump_against_the_recent_average():
    found, _ = rolling.detect(monthly(CALM + [150]), "Sales", SETTINGS)
    assert len(found) == 1
    assert found[0]["period"] == pd.Timestamp("2025-09-01")
    assert 99 < found[0]["expected"] < 102  # the moving average


def test_rolling_does_not_flag_steady_growth():
    growth = [100 + 3 * i + (i % 2) for i in range(20)]
    assert rolling.detect(monthly(growth), "Sales", SETTINGS)[0] == []


def test_rolling_needs_more_values_than_the_window():
    found, reason = rolling.detect(monthly([1, 2, 3, 4]), "Sales", SETTINGS)
    assert found == [] and "needs at least" in reason


def test_rolling_window_can_be_changed():
    small = DetectionSettings(window=3)
    found, _ = rolling.detect(monthly([100, 101, 99, 101, 100, 150]), "Sales", small)
    assert len(found) == 1


# ---------- seasonal ----------
def seasonal_series(years=4, spike_at=None, spike=0):
    rng = np.random.default_rng(7)
    n = 12 * years
    values = (
        np.linspace(100000, 112000, n)
        + 8000 * np.sin(2 * np.pi * np.arange(n) / 12)
        + rng.normal(0, 1200, n)
    )
    if spike_at is not None:
        values[spike_at] += spike
    return monthly(values, "2022-01-01")


def test_seasonal_guesses_the_season_length_from_the_dates():
    assert seasonal.guess_period(monthly(range(30)).index) == 12
    quarterly = pd.date_range("2020-01-01", periods=12, freq="QS")
    assert seasonal.guess_period(quarterly) == 4
    irregular = pd.DatetimeIndex(["2025-01-01", "2025-01-05", "2025-03-20", "2025-07-01"])
    assert seasonal.guess_period(irregular) is None


def test_seasonal_finds_a_real_anomaly_inside_a_seasonal_pattern():
    found, reason = seasonal.detect(seasonal_series(spike_at=30, spike=15000), "Sales", SETTINGS)
    assert reason is None
    assert pd.Timestamp("2024-07-01") in [f["period"] for f in found]


def test_seasonal_does_not_flag_the_normal_yearly_peaks():
    found, _ = seasonal.detect(seasonal_series(), "Sales", SETTINGS)
    peak_months = {3, 4, 5}  # the sine wave peaks in spring, every year
    assert len(found) <= 2
    assert not [f for f in found if f["period"].month in peak_months and f["severity"] == "HIGH"]


def test_plain_zscore_wrongly_flags_the_same_seasonal_peaks():
    # Why the seasonal method exists: a big seasonal swing looks like an anomaly to the z-score.
    series = monthly(
        100000 + 30000 * np.sin(2 * np.pi * np.arange(48) / 12) + np.where(np.arange(48) % 12 == 11, 25000, 0),
        "2022-01-01",
    )
    seasonal_found, _ = seasonal.detect(series, "Sales", SETTINGS)
    zscore_found, _ = zscore.detect(series, "Sales", DetectionSettings(z_threshold=1.5))
    assert len(zscore_found) > len(seasonal_found)


def test_seasonal_needs_two_full_seasons_and_says_so():
    found, reason = seasonal.detect(monthly(range(20)), "Sales", SETTINGS)
    assert found == [] and "24 rows" in reason


def test_seasonal_catches_a_spike_in_the_newest_period():
    # The newest value cannot hide itself, because only older periods are used to judge it.
    found, reason = seasonal.detect(seasonal_series(years=3, spike_at=35, spike=20000), "Sales", SETTINGS)
    assert reason is None
    assert pd.Timestamp("2024-12-01") in [f["period"] for f in found]


def test_seasonal_explanation_mentions_the_same_period_last_season():
    found, _ = seasonal.detect(seasonal_series(years=3, spike_at=35, spike=20000), "Sales", SETTINGS)
    assert "One season ago" in found[-1]["explanation"] or "One season ago" in found[0]["explanation"]


def test_seasonal_needs_evenly_spaced_dates():
    series = pd.Series(range(40), index=pd.to_datetime(sorted(set(pd.date_range("2020-01-01", periods=60, freq="9D")[:40]))), dtype=float)
    series = series.drop(series.index[5])
    assert seasonal.detect(series, "Sales", SETTINGS)[1] is not None


# ---------- isolation forest ----------
def related_table(rows=40, odd_row=None):
    """Three independent metrics. The odd row is 3 standard deviations high on ALL of them."""
    rng = np.random.default_rng(11)
    table = pd.DataFrame(
        {
            "Revenue": rng.normal(100000, 3000, rows),
            "Orders": rng.normal(1200, 40, rows),
            "Returns": rng.normal(60, 5, rows),
        },
        index=pd.date_range("2022-01-01", periods=rows, freq="MS"),
    )
    if odd_row is not None:
        table.iloc[odd_row] = table.mean() + 3 * table.std()
    return table


def test_isolation_forest_catches_a_row_that_is_extreme_in_several_metrics():
    table = related_table(odd_row=20)
    found, reason = isolation.detect(table, list(table.columns), SETTINGS)
    assert reason is None
    assert table.index[20] in [f["period"] for f in found]


def test_isolation_forest_is_quiet_on_normal_data():
    table = related_table()
    found, _ = isolation.detect(table, list(table.columns), SETTINGS)
    assert len(found) <= 2


def test_isolation_forest_gives_the_same_answer_every_time():
    table = related_table(odd_row=20)
    first = isolation.detect(table, list(table.columns), SETTINGS)[0]
    second = isolation.detect(table, list(table.columns), SETTINGS)[0]
    assert [f["period"] for f in first] == [f["period"] for f in second]


def test_isolation_forest_needs_two_metrics_and_enough_rows():
    table = related_table()
    assert isolation.detect(table, ["Revenue"], SETTINGS)[1] is not None
    assert "20 rows" in isolation.detect(table.head(10), list(table.columns), SETTINGS)[1]


def test_isolation_forest_explains_the_row_and_names_a_driver():
    table = related_table(odd_row=20)
    found, _ = isolation.detect(table, list(table.columns), SETTINGS)
    odd = [f for f in found if f["period"] == table.index[20]][0]
    assert odd["metric"] in table.columns
    assert "Biggest driver" in odd["explanation"]
    assert odd["severity"] in ("MEDIUM", "HIGH")


def test_isolation_forest_fills_empty_cells_instead_of_crashing():
    table = related_table(odd_row=20)
    table.iloc[3, 0] = np.nan
    assert isolation.detect(table, list(table.columns), SETTINGS)[1] is None
