from dataclasses import dataclass

HIGH_SCORE = 2.0    # twice as far out as the limit
MEDIUM_SCORE = 1.5  # one and a half times as far out as the limit


@dataclass
class DetectionSettings:
    """All the knobs of the detection engine, with safe defaults.

    The defaults were chosen by running every method on pure random noise and on data with
    a planted anomaly, so that normal data is flagged only about 1 to 4 percent of the time.
    A rolling window of only a few values gives a very rough "normal", so it needs a higher
    limit (3.5) than the z-score (2.0).
    """

    pct_threshold: float = 0.20      # percent change that counts as unusual (0.20 = 20%)
    z_threshold: float = 2.0         # z-score and rolling-window limit
    iqr_multiplier: float = 1.5      # the 1.5 in the box-plot rule
    window: int = 6                  # how many earlier periods the rolling method looks at
    rolling_threshold: float = 3.5   # limit for the rolling method (higher than z_threshold, see note)
    seasonal_threshold: float = 3.0  # limit for the seasonal method
    seasonal_period: int = 0         # 0 = work it out from the dates (12 for monthly data)


def severity_from_score(score):
    """score 1.0 means "just over the limit". 2.0 means twice as far."""
    if score >= HIGH_SCORE:
        return "HIGH"
    if score >= MEDIUM_SCORE:
        return "MEDIUM"
    return "LOW"


def fmt(value):
    """Readable number: 145,000 for big values, 2.45 for small ones."""
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.2f}"


def make_anomaly(period, metric, method, actual, expected, score, explanation):
    """Every method returns records in exactly this shape."""
    actual = float(actual)
    expected = float(expected)
    deviation = None if expected == 0 else (actual - expected) / abs(expected)
    return {
        "period": period,
        "metric": metric,
        "method": method,
        "direction": "up" if actual > expected else "down",
        "actual": actual,
        "expected": expected,
        "deviation_pct": deviation,
        "score": float(score),
        "severity": severity_from_score(score),
        "explanation": explanation,
    }
