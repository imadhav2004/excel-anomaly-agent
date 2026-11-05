import warnings

import numpy as np
import pandas as pd

from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "seasonal"
MIN_SEASONS = 2  # one season to compare with, and one to check

# How many periods make one "season" for a given date step
SEASON_LENGTH = {"MS": 12, "ME": 12, "M": 12, "QS": 4, "QE": 4, "Q": 4, "D": 7, "W": 52, "h": 24, "H": 24}


def guess_period(index):
    """Work out the season length from the dates. Returns None if the dates are irregular."""
    if len(index) < 3:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # newer pandas warns about the return type
            step = pd.infer_freq(index)
    except (ValueError, TypeError):
        return None
    if step is None:
        return None
    step = getattr(step, "freqstr", step)  # newer pandas may return an offset object
    return SEASON_LENGTH.get(step.split("-")[0])


def detect(series, metric, settings):
    """Compare each value with the SAME period one season ago, adjusted for recent growth.

    Step 1: for every period, change = value now - value one season ago (for monthly data,
            this January minus last January). A yearly peak repeats, so its change is normal.
    Step 2: the "normal change" is the median of the changes of the previous `window` periods.
    Step 3: flag the period if its change is far from that normal change
            (measured in the standard deviation of those previous changes).

    Only older periods are used to judge a period, so the newest value cannot hide itself.
    """
    period = settings.seasonal_period or guess_period(series.index)
    if not period:
        return [], "could not work out the season length (dates are not evenly spaced)"
    if len(series) < MIN_SEASONS * period:
        return [], (
            f"needs at least {MIN_SEASONS * period} rows ({MIN_SEASONS} full seasons of {period}), "
            f"the file has {len(series)}"
        )

    window = settings.window
    change = (series - series.shift(period)).to_numpy()
    values = series.to_numpy()

    found = []
    for position in range(period + window, len(series)):
        if np.isnan(change[position]):
            continue
        earlier = pd.Series(change[:position]).dropna().iloc[-window:]
        if len(earlier) < window:
            continue
        normal_change = earlier.median()
        spread = max(earlier.std(), 0.01 * abs(values[position - period]))  # never zero
        if spread == 0:
            continue
        z = (change[position] - normal_change) / spread
        score = abs(z) / settings.seasonal_threshold
        if score < 1:
            continue
        last_season = values[position - period]
        expected = last_season + normal_change
        text = (
            f"{metric} was {fmt(values[position])}. One season ago it was {fmt(last_season)} and it "
            f"has recently been changing by about {fmt(normal_change)} per season, so about "
            f"{fmt(expected)} was expected. The difference is {abs(z):.1f} times the usual variation."
        )
        found.append(make_anomaly(series.index[position], metric, NAME, values[position], expected, score, text))
    return found, None
