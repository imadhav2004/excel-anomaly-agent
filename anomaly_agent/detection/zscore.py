from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "zscore"
MIN_VALUES = 4


def detect(series, metric, settings):
    """Flag values that are many standard deviations away from the overall average."""
    values = series.dropna()
    if len(values) < MIN_VALUES:
        return [], f"needs at least {MIN_VALUES} values"

    mean = values.mean()
    std = values.std()  # sample standard deviation
    if std == 0:
        return [], "all values are the same"

    found = []
    for period, actual in values.items():
        z = (actual - mean) / std
        score = abs(z) / settings.z_threshold
        if score < 1:
            continue
        text = (
            f"{metric} was {fmt(actual)}, which is {abs(z):.1f} standard deviations "
            f"{'above' if z > 0 else 'below'} the average of {fmt(mean)}. "
            f"The limit is {settings.z_threshold:.1f}."
        )
        found.append(make_anomaly(period, metric, NAME, actual, mean, score, text))
    return found, None
