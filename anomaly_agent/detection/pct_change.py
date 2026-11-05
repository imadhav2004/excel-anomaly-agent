from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "pct_change"


def detect(series, metric, settings):
    """Flag a period whose value jumped or dropped a lot compared with the one before."""
    values = series.dropna()
    if len(values) < 2:
        return [], "needs at least 2 values"

    found = []
    previous_values = values.shift(1)
    for period, actual, previous in zip(values.index[1:], values.iloc[1:], previous_values.iloc[1:]):
        if previous == 0:
            if actual == 0:
                continue
            score = 2.0  # a change from zero cannot be measured in percent
            text = f"{metric} went from 0 to {fmt(actual)}. A change from zero cannot be given in percent."
        else:
            change = (actual - previous) / abs(previous)
            score = abs(change) / settings.pct_threshold
            if score < 1:
                continue
            word = "rose" if change > 0 else "fell"
            text = (
                f"{metric} {word} {abs(change):.0%} from {fmt(previous)} to {fmt(actual)}. "
                f"The limit is {settings.pct_threshold:.0%}."
            )
        found.append(make_anomaly(period, metric, NAME, actual, previous, score, text))
    return found, None
