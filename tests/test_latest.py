import numpy as np
import pandas as pd

from anomaly_agent.detection.base import DetectionSettings
from anomaly_agent.detection.engine import METHODS, run_detection, summarise
from anomaly_agent.latest import latest_anomalies, latest_period_anomalies


def table(values, other=None):
    df = pd.DataFrame({"When": pd.date_range("2025-01-01", periods=len(values), freq="MS"), "Sales": values})
    if other is not None:
        df["Refunds"] = other
    return df


QUIET = [1000 + 10 * (i % 3) for i in range(11)]


def test_the_newest_period_uses_the_same_severity_as_the_scan():
    df = table(QUIET + [1500])
    result = run_detection(df, "When", ["Sales"], list(METHODS), DetectionSettings())
    summary = summarise(result)
    scan_row = [r for r in summary if r["period"] == df["When"].iloc[-1]][0]
    found = latest_anomalies(df, "When", summary)
    assert len(found) == 1
    assert found[0]["severity"] == scan_row["severity"]  # one scan, one severity
    assert found[0]["votes"] == scan_row["votes"]


def test_records_have_everything_the_email_the_reports_and_the_ai_need():
    df = table(QUIET + [1500])
    record = latest_period_anomalies(df, "When")[0]
    assert set(record) >= {"metric", "direction", "latest", "previous", "pct_change", "z_score", "severity"}
    assert record["metric"] == "Sales" and record["direction"] == "up"
    assert record["latest"] == 1500.0 and record["previous"] == 1010.0
    assert round(record["pct_change"], 3) == 0.485
    assert record["z_score"] > 3
    assert all(isinstance(record[k], float) for k in ("latest", "previous", "pct_change", "z_score"))


def test_older_anomalies_are_not_reported_as_new():
    values = QUIET[:5] + [2500] + QUIET[6:] + [1010]  # the spike is in the past, the newest value is normal
    assert latest_period_anomalies(table(values), "When") == []


def test_a_change_from_zero_has_no_percent():
    df = table([0.0] * 8 + [0.0, 0.0, 0.0, 400.0])
    record = latest_period_anomalies(df, "When")
    assert record and record[0]["pct_change"] is None


def test_an_empty_previous_cell_does_not_crash():
    df = table(QUIET + [np.nan, 1500.0])
    found = latest_period_anomalies(df, "When")
    assert isinstance(found, list)
    assert all(r["previous"] is None or isinstance(r["previous"], float) for r in found)


def test_most_severe_first_and_no_methods_means_nothing():
    df = table(QUIET + [1500], other=[50, 51, 52] * 3 + [50, 51, 70])
    found = latest_period_anomalies(df, "When")
    ranks = [{"HIGH": 0, "MEDIUM": 1, "LOW": 2}[r["severity"]] for r in found]
    assert ranks == sorted(ranks)
    assert latest_anomalies(df, "When", []) == []
