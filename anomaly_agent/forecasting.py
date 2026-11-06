"""Forecasting: predict the next periods of one metric, with an honest accuracy check.

The model is Holt-Winters style exponential smoothing (statsmodels ETSModel):
  level    = where the series is now
  trend    = how fast it is rising or falling
  seasonal = the repeating yearly shape (only when there are at least 2 full seasons)

We try a few simple versions (with or without trend, with or without season) and keep the one
with the lowest AICc, a score that rewards a good fit but punishes a model that is too complex.

Accuracy check ("backtest"): hide the newest periods, forecast them from the older data,
and compare with what really happened. We also compare against a naive guess
("same as last season" or "same as the last value"). A forecast that cannot beat the naive
guess is not worth trusting, so the page says so.
"""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from anomaly_agent.detection.seasonal import guess_period

MIN_ROWS = 8           # below this a forecast is only a guess
MAX_HORIZON = 24
BAND = 0.95            # the confidence band covers 95% of likely outcomes


class ForecastError(Exception):
    """A problem the user can fix (too few rows, uneven dates). The message is shown on the page."""


def prepare_series(df, date_column, metric):
    """Return (series with a regular date index, season length, number of gaps filled)."""
    data = df[[date_column, metric]].dropna(subset=[date_column]).sort_values(date_column)
    series = data.set_index(date_column)[metric].astype(float)
    if series.index.has_duplicates:
        raise ForecastError("Some dates appear more than once. Remove duplicate rows in the sidebar first.")
    if len(series) < MIN_ROWS:
        raise ForecastError(f"Need at least {MIN_ROWS} rows to forecast, this file has {len(series)}.")
    freq = _frequency(series.index)
    if freq is None:
        raise ForecastError("The dates are not evenly spaced (for example monthly), so a forecast is not possible.")
    series = series.asfreq(freq)
    gaps = int(series.isna().sum())
    if gaps:
        series = series.interpolate(limit_area="inside")
    if series.isna().any():
        raise ForecastError(f"{metric} has empty cells at the start or end. Fill or remove them first.")
    if series.nunique() < 2:
        raise ForecastError(f"{metric} has the same value in every period, there is nothing to forecast.")
    return series, guess_period(series.index) or 0, gaps


def _frequency(index):
    """Date step of the index as a string such as 'MS', or None if it is irregular.

    A monthly file with one missing month is still monthly: we look at the typical step.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        freq = pd.infer_freq(index) if len(index) >= 3 else None
    if freq is not None:
        return getattr(freq, "freqstr", freq)
    # one or two missing dates: try the common steps and accept if every date fits
    for freq in ("MS", "QS", "D", "W", "h"):
        full = pd.date_range(index[0], index[-1], freq=freq)
        if len(full) <= len(index) * 1.25 and index.isin(full).all():
            return freq
    return None


def _candidates(n, period):
    """Model versions worth trying for a series of n values."""
    options = [("add", None), (None, None)]
    if period and n >= 2 * period:
        options = [("add", "add"), (None, "add")] + options
    return options


def _fit(values, trend, seasonal, period):
    # "heuristic" starts the seasonal values from the data instead of estimating every one of
    # them, which works much better when there are only 2 to 4 years of data.
    kwargs = {
        "error": "add",
        "trend": trend,
        "damped_trend": trend is not None,
        "initialization_method": "heuristic" if len(values) >= 10 else "estimated",  # heuristic needs 10+ rows
    }
    if seasonal:
        kwargs.update(seasonal=seasonal, seasonal_periods=period)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ETSModel(values, **kwargs).fit(disp=False)


def _best_fit(series, period):
    """Fit all candidate versions and return (fit, label) of the one with the lowest AICc."""
    best = None
    for trend, seasonal in _candidates(len(series), period):
        try:
            fit = _fit(series, trend, seasonal, period)
        except Exception:  # a version that cannot be fitted is simply skipped
            continue
        score = fit.aicc
        if not np.isfinite(score):  # AICc is undefined when there are very few rows
            score = fit.aic
        if not np.isfinite(score):
            continue
        if best is None or score < best[0]:
            best = (score, fit, _label(trend, seasonal))
    if best is None:
        raise ForecastError("The model could not be fitted to this data.")
    return best[1], best[2]


def _label(trend, seasonal):
    parts = ["level"]
    if trend:
        parts.append("trend")
    if seasonal:
        parts.append("yearly pattern")
    return " + ".join(parts)


def _predict(fit, horizon):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame = fit.get_prediction(start=len(fit.fittedvalues), end=len(fit.fittedvalues) + horizon - 1)
        table = frame.summary_frame(alpha=1 - BAND)
    return table["mean"].to_numpy(), table["pi_lower"].to_numpy(), table["pi_upper"].to_numpy()


def _naive(train, steps, period):
    """The simple guess to beat: same as one season ago, or the last value if no season."""
    if period and len(train) >= period:
        pattern = train.iloc[-period:].to_numpy()
        return np.array([pattern[i % period] for i in range(steps)])
    return np.repeat(train.iloc[-1], steps)


def _error_scores(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mae = float(np.mean(np.abs(actual - predicted)))
    nonzero = actual != 0
    mape = float(np.mean(np.abs((actual[nonzero] - predicted[nonzero]) / actual[nonzero]))) if nonzero.any() else None
    return mae, mape


def backtest(series, period, steps):
    """Hide the last `steps` values, forecast them, compare with the truth."""
    steps = max(1, min(steps, len(series) - MIN_ROWS + 2, len(series) // 3))
    train, test = series.iloc[:-steps], series.iloc[-steps:]
    fit, _ = _best_fit(train, period if len(train) >= 2 * period else 0)
    predicted, low, high = _predict(fit, steps)
    mae, mape = _error_scores(test, predicted)
    naive_mae, naive_mape = _error_scores(test, _naive(train, steps, period))
    inside = float(np.mean((test.to_numpy() >= low) & (test.to_numpy() <= high)))
    return {
        "steps": steps,
        "dates": list(test.index),
        "actual": test.to_numpy(),
        "predicted": predicted,
        "mae": mae,
        "mape": mape,
        "naive_mae": naive_mae,
        "naive_mape": naive_mape,
        "beats_naive": mae < naive_mae,
        "inside_band": inside,
    }


def verdict(test):
    """One plain sentence about how far the forecast can be trusted."""
    mape = test["mape"]
    if mape is None:
        return "poor", "Accuracy could not be measured because the hidden values were zero."
    if not test["beats_naive"]:
        return "poor", (
            f"On the hidden last {test['steps']} periods this forecast was off by {mape:.1%} on average, "
            "and a simple guess (repeat last season) did at least as well. Treat the forecast with care."
        )
    if mape < 0.10:
        grade, text = "good", "good"
    elif mape < 0.20:
        grade, text = "fair", "fair"
    else:
        grade, text = "poor", "weak"
    return grade, (
        f"Accuracy is {text}: on the hidden last {test['steps']} periods the forecast was off by "
        f"{mape:.1%} on average and beat the simple guess."
    )


def forecast_metric(df, date_column, metric, horizon=6):
    """Forecast `horizon` periods of one metric. Returns everything the page needs."""
    if not 1 <= horizon <= MAX_HORIZON:
        raise ForecastError(f"Choose a horizon between 1 and {MAX_HORIZON} periods.")
    series, period, gaps = prepare_series(df, date_column, metric)
    fit, label = _best_fit(series, period)
    mean, low, high = _predict(fit, horizon)
    future = pd.date_range(series.index[-1], periods=horizon + 1, freq=series.index.freq)[1:]
    test = backtest(series, period, min(horizon, 6))
    grade, sentence = verdict(test)
    return {
        "metric": metric,
        "history": series,
        "dates": list(future),
        "forecast": mean,
        "lower": low,
        "upper": high,
        "model": label,
        "season_length": period,
        "gaps_filled": gaps,
        "test": test,
        "grade": grade,
        "verdict": sentence,
    }
