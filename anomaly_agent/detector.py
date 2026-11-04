import pandas as pd

MIN_HISTORY = 3  # older values needed before we trust our idea of "normal"


def calc_pct_change(previous, latest):
    if previous == 0:
        return None  # cannot divide by zero
    return (latest - previous) / previous


def calc_z_score(latest, history):
    mean = history.mean()
    std = history.std()
    if std == 0 or pd.isna(std):
        return 0.0
    return (latest - mean) / std


def get_severity(pct_change, z_score):
    pct = abs(pct_change) if pct_change is not None else 0.0
    z = abs(z_score)

    if z >= 3 or pct >= 0.50:
        return "HIGH"
    if z >= 2 or pct >= 0.30:
        return "MEDIUM"
    return "LOW"


def detect_anomalies(df, date_column="Month", pct_threshold=0.20, z_threshold=2.0):
    metrics = [c for c in df.select_dtypes(include="number").columns if c != date_column]

    anomalies = []
    for metric in metrics:
        latest = df[metric].iloc[-1]
        previous = df[metric].iloc[-2]
        history = df[metric].iloc[:-1].dropna()

        if pd.isna(latest) or pd.isna(previous):
            continue
        if len(history) < MIN_HISTORY:
            continue

        pct_change = calc_pct_change(previous, latest)
        z_score = calc_z_score(latest, history)

        if previous == 0:
            big_jump = latest != 0
        else:
            big_jump = abs(pct_change) >= pct_threshold
        far_from_normal = abs(z_score) >= z_threshold

        if big_jump or far_from_normal:
            anomalies.append(
                {
                    "metric": metric,
                    "direction": "up" if latest > previous else "down",
                    "latest": float(latest),
                    "previous": float(previous),
                    "pct_change": None if pct_change is None else float(pct_change),
                    "z_score": float(z_score),
                    "severity": get_severity(pct_change, z_score),
                }
            )
    return anomalies
