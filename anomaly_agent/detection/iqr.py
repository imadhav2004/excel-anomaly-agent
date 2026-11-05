from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "iqr"
MIN_VALUES = 4


def detect(series, metric, settings):
    """Box-plot rule: flag values outside Q1 - k*IQR ... Q3 + k*IQR.

    Q1 and Q3 are the 25% and 75% marks of the sorted values and IQR = Q3 - Q1.
    Unlike the z-score, one huge outlier cannot hide itself by inflating the spread.
    """
    values = series.dropna()
    if len(values) < MIN_VALUES:
        return [], f"needs at least {MIN_VALUES} values"

    q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    if iqr == 0:
        return [], "the middle half of the values is identical, so there is no spread to measure"

    lower = q1 - settings.iqr_multiplier * iqr
    upper = q3 + settings.iqr_multiplier * iqr

    found = []
    for period, actual in values.items():
        if actual > median:
            score = (actual - median) / (upper - median)
        else:
            score = (median - actual) / (median - lower)
        if score < 1:
            continue
        side = "above" if actual > median else "below"
        text = (
            f"{metric} was {fmt(actual)}, {side} the normal range {fmt(lower)} to {fmt(upper)} "
            f"(box-plot rule, usual value about {fmt(median)})."
        )
        found.append(make_anomaly(period, metric, NAME, actual, median, score, text))
    return found, None
