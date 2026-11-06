import numpy as np
import pandas as pd
import pytest

from anomaly_agent.forecasting import ForecastError, backtest, forecast_metric, prepare_series, verdict


def monthly(values, start="2022-01-01"):
    return pd.DataFrame({"Month": pd.date_range(start, periods=len(values), freq="MS"), "Value": values})


def seasonal_values(years=4, trend=20.0, noise=0.0, seed=1):
    """Level 1000, a steady rise, a yearly wave. noise=0 gives a perfectly clean series."""
    rng = np.random.default_rng(seed)
    t = np.arange(12 * years)
    wave = 150 * np.sin(2 * np.pi * (t % 12) / 12)
    return 1000 + trend * t + wave + rng.normal(0, noise, len(t))


def test_forecast_follows_a_yearly_pattern_and_trend():
    df = monthly(seasonal_values(noise=5))
    result = forecast_metric(df, "Month", "Value", horizon=12)
    t = np.arange(48, 60)
    truth = 1000 + 20.0 * t + 150 * np.sin(2 * np.pi * (t % 12) / 12)
    error = np.mean(np.abs(result["forecast"] - truth) / truth)
    assert error < 0.05
    assert "yearly pattern" in result["model"]
    # next year's peak falls in the same month, and the whole shape follows the real curve
    assert int(np.argmax(result["forecast"])) == int(np.argmax(truth))
    assert np.corrcoef(result["forecast"], truth)[0, 1] > 0.9


def test_dates_continue_from_the_last_period_and_band_surrounds_forecast():
    df = monthly(seasonal_values(noise=5))
    result = forecast_metric(df, "Month", "Value", horizon=5)
    assert result["dates"][0] == pd.Timestamp("2026-01-01")
    assert result["dates"][-1] == pd.Timestamp("2026-05-01")
    assert len(result["forecast"]) == len(result["lower"]) == len(result["upper"]) == 5
    assert np.all(result["lower"] < result["forecast"])
    assert np.all(result["forecast"] < result["upper"])


def test_band_gets_wider_further_ahead():
    df = monthly(seasonal_values(noise=30))
    result = forecast_metric(df, "Month", "Value", horizon=8)
    width = result["upper"] - result["lower"]
    assert width[-1] > width[0]


def test_trend_only_series_keeps_rising_without_a_yearly_pattern():
    df = monthly([100 + 5 * i for i in range(14)])  # 14 rows: not two full years
    result = forecast_metric(df, "Month", "Value", horizon=3)
    assert "yearly pattern" not in result["model"]
    assert result["forecast"][0] > 100 + 5 * 13 - 1
    assert result["forecast"][2] > result["forecast"][0]


def test_too_few_rows_gives_a_friendly_error():
    with pytest.raises(ForecastError, match="at least"):
        forecast_metric(monthly([1, 2, 3, 4, 5]), "Month", "Value", horizon=3)


def test_uneven_dates_give_an_error():
    df = monthly(list(range(20)))
    df["Month"] = pd.to_datetime(
        ["2022-01-01", "2022-01-05", "2022-03-20", "2022-04-02", "2022-07-01", "2022-07-09", "2022-10-30",
         "2022-11-02", "2023-01-17", "2023-02-02", "2023-05-05", "2023-05-06", "2023-08-01", "2023-08-30",
         "2023-12-25", "2024-01-03", "2024-04-04", "2024-04-05", "2024-09-09", "2024-12-31"]
    )
    with pytest.raises(ForecastError, match="evenly spaced"):
        forecast_metric(df, "Month", "Value", horizon=3)


def test_duplicate_dates_give_an_error():
    df = monthly(list(range(12)))
    df.loc[5, "Month"] = df.loc[4, "Month"]
    with pytest.raises(ForecastError, match="more than once"):
        forecast_metric(df, "Month", "Value", horizon=3)


def test_constant_series_gives_an_error():
    with pytest.raises(ForecastError, match="same value"):
        forecast_metric(monthly([50.0] * 12), "Month", "Value", horizon=3)


def test_horizon_must_be_in_range():
    with pytest.raises(ForecastError, match="horizon"):
        forecast_metric(monthly(seasonal_values(2)), "Month", "Value", horizon=0)


def test_empty_cell_in_the_middle_is_filled_and_counted():
    values = list(seasonal_values(2, noise=5))
    values[10] = np.nan
    series, period, gaps = prepare_series(monthly(values), "Month", "Value")
    assert gaps == 1
    assert not series.isna().any()
    assert period == 12


def test_a_missing_month_row_is_treated_as_a_gap_not_as_uneven_dates():
    df = monthly(list(seasonal_values(2, noise=5))).drop(index=9).reset_index(drop=True)
    series, _, gaps = prepare_series(df, "Month", "Value")
    assert gaps == 1
    assert len(series) == 24


def test_empty_cells_at_the_end_are_refused():
    values = list(seasonal_values(2, noise=5))
    values[-1] = np.nan
    with pytest.raises(ForecastError, match="start or end"):
        prepare_series(monthly(values), "Month", "Value")


def test_backtest_hides_the_newest_periods_and_never_sees_them():
    df = monthly(seasonal_values(noise=5))
    series, period, _ = prepare_series(df, "Month", "Value")
    first = backtest(series, period, 6)
    assert first["dates"] == list(series.index[-6:])
    changed = series.copy()
    changed.iloc[-6:] = changed.iloc[-6:] * 5  # change only the hidden values
    second = backtest(changed, period, 6)
    assert np.allclose(first["predicted"], second["predicted"])  # no peeking at the answer
    assert second["mape"] > first["mape"]


def test_good_forecast_beats_the_simple_guess():
    df = monthly(seasonal_values(noise=5))
    result = forecast_metric(df, "Month", "Value", horizon=6)
    assert result["test"]["beats_naive"]
    assert result["test"]["mape"] < 0.05
    assert result["grade"] == "good"


def test_verdict_warns_when_the_simple_guess_is_as_good():
    grade, text = verdict({"mape": 0.12, "beats_naive": False, "steps": 6})
    assert grade == "poor"
    assert "simple guess" in text


def test_verdict_grades_by_error_size():
    assert verdict({"mape": 0.05, "beats_naive": True, "steps": 6})[0] == "good"
    assert verdict({"mape": 0.15, "beats_naive": True, "steps": 6})[0] == "fair"
    assert verdict({"mape": 0.35, "beats_naive": True, "steps": 6})[0] == "poor"
    assert verdict({"mape": None, "beats_naive": True, "steps": 6})[0] == "poor"


def test_works_on_the_demo_file_values():
    # same shape as data/demo_4_years.xlsx: yearly wave with growth plus a one-off spike
    values = seasonal_values(noise=20)
    values[30] *= 0.7
    result = forecast_metric(monthly(values), "Month", "Value", horizon=6)
    assert result["season_length"] == 12
    assert result["test"]["mape"] < 0.15
