from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from anomaly_agent.detection import iqr, isolation, pct_change, rolling, seasonal, zscore
from anomaly_agent.detection.base import DetectionSettings, severity_from_score


@dataclass
class MethodInfo:
    label: str
    description: str
    detect: object
    multivariate: bool = False  # True = looks at all metrics together


METHODS = {
    pct_change.NAME: MethodInfo(
        "Percent change", "Jump or drop compared with the previous period.", pct_change.detect
    ),
    zscore.NAME: MethodInfo(
        "Z-score", "Distance from the overall average, in standard deviations.", zscore.detect
    ),
    iqr.NAME: MethodInfo(
        "IQR (box plot)", "Outside the normal range of the middle half of the values.", iqr.detect
    ),
    rolling.NAME: MethodInfo(
        "Rolling window", "Far from the moving average of the last few periods.", rolling.detect
    ),
    seasonal.NAME: MethodInfo(
        "Seasonal", "Unusual compared with the same period one season ago, allowing for recent growth.", seasonal.detect
    ),
    isolation.NAME: MethodInfo(
        "Isolation Forest", "Unusual as a combination of all metrics.", isolation.detect, multivariate=True
    ),
}


def run_detection(df, date_column, metrics=None, methods=None, settings=None):
    """Scan EVERY period of the chosen metrics with the chosen methods.

    Returns a dictionary:
      anomalies - every flagged record (see base.make_anomaly for the shape)
      skipped   - methods that could not run, each with the reason
      ran       - for each metric, the methods that really ran on it
    """
    settings = settings or DetectionSettings()
    if metrics is None:
        metrics = [c for c in df.select_dtypes(include="number").columns if c != date_column]
    methods = list(METHODS) if methods is None else list(methods)
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise ValueError(f"Unknown detection method(s): {unknown}. Choose from {list(METHODS)}")

    table = df.set_index(date_column).sort_index()
    table.index = pd.DatetimeIndex(pd.to_datetime(table.index))

    anomalies, skipped = [], []
    ran = {metric: [] for metric in metrics}

    for key in methods:
        info = METHODS[key]
        if info.multivariate:
            found, reason = info.detect(table, metrics, settings)
            if reason:
                skipped.append({"method": key, "metric": "all metrics", "reason": reason})
                continue
            anomalies.extend(found)
            for metric in metrics:
                ran[metric].append(key)
            continue

        for metric in metrics:
            found, reason = info.detect(table[metric], metric, settings)
            if reason:
                skipped.append({"method": key, "metric": metric, "reason": reason})
                continue
            anomalies.extend(found)
            ran[metric].append(key)

    anomalies.sort(key=lambda a: (a["period"], a["score"]), reverse=True)
    return {"anomalies": anomalies, "skipped": skipped, "ran": ran}


def summarise(result):
    """Combine the methods: one row per (period, metric) with how many methods agree.

    A value flagged by 3 of 4 methods is much more believable than one flagged by a single method.
    """
    groups = defaultdict(list)
    for record in result["anomalies"]:
        groups[(record["period"], record["metric"])].append(record)

    rows = []
    for (period, metric), records in groups.items():
        best = max(records, key=lambda r: r["score"])
        methods = sorted({r["method"] for r in records}, key=list(METHODS).index)
        rows.append(
            {
                "period": period,
                "metric": metric,
                "direction": best["direction"],
                "actual": best["actual"],
                "expected": best["expected"],
                "deviation_pct": best["deviation_pct"],
                "score": best["score"],
                "severity": severity_from_score(best["score"]),
                "methods": methods,
                "votes": len(methods),
                "methods_run": len(result["ran"].get(metric, [])),
                "explanation": best["explanation"],
            }
        )
    rows.sort(key=lambda r: (r["period"], r["votes"], r["score"]), reverse=True)
    return rows


def group_skipped(result):
    """Skipped methods, with metrics that share a reason put together."""
    grouped = defaultdict(list)
    for item in result["skipped"]:
        grouped[(item["method"], item["reason"])].append(item["metric"])
    return [
        {"method": method, "reason": reason, "metrics": metrics}
        for (method, reason), metrics in grouped.items()
    ]
