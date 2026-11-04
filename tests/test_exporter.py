from io import BytesIO

import pandas as pd

from anomaly_agent.exporter import build_excel_report
from anomaly_agent.report import anomalies_to_rows


def make_anomaly(metric, severity):
    return {
        "metric": metric,
        "direction": "up",
        "latest": 150.0,
        "previous": 100.0,
        "pct_change": 0.5,
        "z_score": 4.0,
        "severity": severity,
    }


def make_df():
    return pd.DataFrame(
        {"Month": pd.date_range("2025-01-01", periods=4, freq="MS"), "Revenue": [100, 101, 99, 150]}
    )


def test_rows_are_sorted_high_first():
    rows = anomalies_to_rows([make_anomaly("Orders", "LOW"), make_anomaly("Revenue", "HIGH")])
    assert [r["Metric"] for r in rows] == ["Revenue", "Orders"]


def test_report_has_three_sheets():
    data = build_excel_report(make_df(), [make_anomaly("Revenue", "HIGH")], "Apr 2025")
    sheets = pd.read_excel(BytesIO(data), sheet_name=None)
    assert list(sheets) == ["Summary", "Anomalies", "Data"]
    assert sheets["Anomalies"]["Metric"].tolist() == ["Revenue"]
    assert len(sheets["Data"]) == 4


def test_report_works_with_no_anomalies():
    data = build_excel_report(make_df(), [], "Apr 2025")
    sheets = pd.read_excel(BytesIO(data), sheet_name=None)
    assert len(sheets["Anomalies"]) == 0
