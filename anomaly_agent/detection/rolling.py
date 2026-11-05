from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "rolling"
MIN_SPREAD = 0.01  # if the recent values are identical, use 1% of their average as the spread


def detect(series, metric, settings):
    """Compare each value with the moving average and rolling standard deviation of the
    `window` periods before it. This follows a trend, so slow growth is not flagged."""
    values = series.dropna()
    window = settings.window
    if window < 2:
        return [], "the window must be at least 2"
    if len(values) < window + 1:
        return [], f"needs at least {window + 1} values for a window of {window}"

    found = []
    for position in range(window, len(values)):
        recent = values.iloc[position - window:position]
        mean = recent.mean()
        std = max(recent.std(), MIN_SPREAD * abs(mean))
        if std == 0:
            continue
        actual = values.iloc[position]
        z = (actual - mean) / std
        score = abs(z) / settings.rolling_threshold
        if score < 1:
            continue
        text = (
            f"{metric} was {fmt(actual)}. The moving average of the previous {window} periods is "
            f"{fmt(mean)}, so this is {abs(z):.1f} rolling standard deviations "
            f"{'above' if z > 0 else 'below'} it."
        )
        found.append(make_anomaly(values.index[position], metric, NAME, actual, mean, score, text))
    return found, None
