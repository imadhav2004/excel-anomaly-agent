"""The anomalies of the newest period, taken from the same scan as everything else.

Before Phase 6 the page had two detectors: an old one for the newest period and the new scan for all
periods, and they could give different severities for the same value. Now the newest period is simply
the scan result for the last date, written in the older record format that the email, the Excel and
PDF reports and the AI explainer already understand. One scan, one severity everywhere.
"""
import pandas as pd

from anomaly_agent.detection.base import DetectionSettings
from anomaly_agent.detection.engine import METHODS, run_detection, summarise
from anomaly_agent.detector import MIN_HISTORY, calc_pct_change, calc_z_score


def latest_anomalies(df, date_column, summary):
    """Rows of `summary` that belong to the last date of `df`, as older-format records."""
    last_date = df[date_column].iloc[-1]
    records = []
    for row in summary:
        if row["period"] != last_date:
            continue
        series = df[row["metric"]]
        latest, previous = float(series.iloc[-1]), series.iloc[-2]
        history = series.iloc[:-1].dropna()
        pct = None if pd.isna(previous) else calc_pct_change(float(previous), latest)
        z = calc_z_score(latest, history) if len(history) >= MIN_HISTORY else 0.0
        records.append(
            {
                "metric": row["metric"],
                "direction": row["direction"],
                "latest": latest,
                "previous": None if pd.isna(previous) else float(previous),
                "pct_change": None if pct is None else float(pct),
                "z_score": float(z),
                "severity": row["severity"],
                "votes": row["votes"],
                "methods_run": row["methods_run"],
            }
        )
    return sorted(records, key=lambda r: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[r["severity"]], r["metric"]))


def latest_period_anomalies(df, date_column, settings=None, methods=None):
    """Run the scan and return the newest period's anomalies (used by main.py, the e-mail job)."""
    metrics = [c for c in df.select_dtypes(include="number").columns if c != date_column]
    result = run_detection(df, date_column, metrics, list(methods or METHODS), settings or DetectionSettings())
    return latest_anomalies(df, date_column, summarise(result))
