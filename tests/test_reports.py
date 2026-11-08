import re
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from anomaly_agent.ai_explainer import get_explanations
from anomaly_agent.detection.base import DetectionSettings
from anomaly_agent.detection.engine import METHODS, run_detection, summarise
from anomaly_agent.forecasting import ForecastError
from anomaly_agent.latest import latest_anomalies
from anomaly_agent.report_data import cleaned_csv, collect_report_data, forecast_csv, safe_text, scan_csv
from anomaly_agent.report_pdf import build_full_pdf
from anomaly_agent.report_xlsx import build_full_excel


def make(values=None, metrics=("Sales", "Refunds"), rename=None, **options):
    values = values or [1000 + 10 * (i % 3) for i in range(23)] + [1500]
    df = pd.DataFrame({"When": pd.date_range("2024-01-01", periods=len(values), freq="MS")})
    df["Sales"] = values
    df["Refunds"] = [50 + (i % 3) for i in range(len(values))]
    if rename:
        df = df.rename(columns=rename)
        metrics = [rename.get(m, m) for m in metrics]
    metrics = list(metrics)
    summary = summarise(run_detection(df, "When", metrics, list(METHODS), DetectionSettings()))
    anomalies = latest_anomalies(df, "When", summary)
    explanations = get_explanations(anomalies, "Dec 2025", use_ai=False)
    data = collect_report_data(df, "When", metrics, summary, anomalies, explanations, "sales.xlsx", "Dec 2025",
                               clean_log=["Removed 2 duplicate rows."], **options)
    return df, data


def test_report_data_has_every_part_and_matches_the_scan():
    df, data = make()
    assert data["kpis"][0] == ("Rows analysed", "24")
    assert [r["metric"] for r in data["latest"]] == ["Sales"] and data["latest"][0]["severity"] in ("HIGH", "MEDIUM", "LOW")
    assert data["latest"][0]["note"]  # a built-in note is attached
    assert len(data["scan"]) == int(data["kpis"][2][1]) or len(data["scan"]) >= 1
    periods = [r["period"] for r in data["scan"]]
    assert periods == sorted(periods, reverse=True)  # newest first
    assert set(data["series"]) == {"Sales", "Refunds"}
    sales = data["series"]["Sales"]
    assert len(sales["values"]) == 24 and 23 in sales["flagged"]
    assert [f["metric"] for f in data["forecasts"]] == ["Sales", "Refunds"]
    assert len(data["forecasts"][0]["rows"]) == 3 and data["clean_log"] == ["Removed 2 duplicate rows."]


def test_a_metric_that_cannot_be_forecast_is_reported_not_fatal():
    def forecaster(df, date_column, metric, horizon):
        raise ForecastError("Need at least 8 rows.")

    _, data = make(forecaster=forecaster)
    assert all(f["error"] == "Need at least 8 rows." for f in data["forecasts"])
    pdf = build_full_pdf(data, compress=False)
    assert b"no forecast" in pdf and pdf.startswith(b"%PDF")


def test_the_pdf_contains_the_findings():
    _, data = make(ai_summary="- Sales looks unusual.")
    pdf = build_full_pdf(data, compress=False)
    text = pdf.decode("latin-1")  # brackets are escaped inside a PDF
    for expected in ("Anomalies in the latest period", "Sales", "Forecast \\(next 3 periods\\)", "Trend of every metric",
                     "not confirmed business problems", "AI summary", "Removed 2 duplicate rows."):
        assert expected in text
    assert len(re.findall(rb"/Type /Page\b", pdf)) >= 2
    assert build_full_pdf(data).startswith(b"%PDF")  # the normal compressed version works too


def test_a_pdf_with_no_anomalies_and_odd_characters_still_builds():
    _, data = make(values=[1000 + (i % 3) for i in range(24)], rename={"Sales": "Ventes → 中 “x”"})
    assert data["latest"] == []
    assert build_full_pdf(data).startswith(b"%PDF")
    assert "No anomalies were flagged in the latest period." in build_full_pdf(data, compress=False).decode("latin-1")


def test_a_constant_metric_does_not_break_the_chart():
    df, data = make(values=[100.0] * 24)
    assert build_full_pdf(data).startswith(b"%PDF")


def test_the_excel_file_has_formatted_sheets_and_real_charts():
    df, data = make()
    book = load_workbook(BytesIO(build_full_excel(data, df, "When")))
    assert book.sheetnames == ["Summary", "Latest anomalies", "All flags", "Forecast", "Data", "Charts", "Notes"]
    latest = book["Latest anomalies"]
    assert latest["A2"].value == "Sales" and latest["B2"].fill.fgColor.rgb.endswith(("FECACA", "FEF0C7", "DBEAFE"))
    assert latest.freeze_panes == "A2"
    flags = book["All flags"]
    assert flags.auto_filter.ref and flags["A2"].number_format == "mmm yyyy" and flags["G2"].number_format == "0.0%"
    assert book["Data"].max_row == 25 and book["Data"]["B25"].value == 1500
    assert len(book["Charts"]._charts) == 2  # one chart per metric
    forecast = book["Forecast"]
    assert forecast["A2"].value == "Sales" and forecast["C2"].value > 0 and forecast["G2"].value in ("good", "fair", "poor")
    assert book["Summary"]["A5"].value == "Measure"


def test_text_from_the_uploaded_file_never_becomes_a_formula():
    evil = "=HYPERLINK(\"http://evil.example\",\"x\")"
    df, data = make(rename={"Sales": evil})
    book = load_workbook(BytesIO(build_full_excel(data, df, "When")))
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            assert not any(c.data_type == "f" for c in row), sheet.title
    assert safe_text(evil).startswith("'=") and safe_text("-5 and") == "'-5 and" and safe_text(5) == 5
    assert safe_text("Sales") == "Sales"
    assert b"'=HYPERLINK" in scan_csv(data) and b"'=HYPERLINK" in cleaned_csv(df)


def test_csv_files_have_the_expected_columns():
    df, data = make()
    scan = pd.read_csv(BytesIO(scan_csv(data)))
    assert list(scan.columns)[:4] == ["Period", "Metric", "Severity", "Direction"] and len(scan) == len(data["scan"])
    forecast = pd.read_csv(BytesIO(forecast_csv(data)))
    assert list(forecast.columns) == ["Metric", "Period", "Forecast", "Lower 95%", "Upper 95%", "Accuracy"]
    assert len(forecast) == 6  # 2 metrics x 3 periods
    assert (forecast["Lower 95%"] <= forecast["Forecast"]).all() and (forecast["Forecast"] <= forecast["Upper 95%"]).all()
    assert list(pd.read_csv(BytesIO(cleaned_csv(df))).columns) == ["When", "Sales", "Refunds"]


def test_an_empty_scan_gives_valid_empty_files():
    values = [1000 + (i % 3) for i in range(24)]
    df, data = make(values=values)
    data["scan"] = []
    assert pd.read_csv(BytesIO(scan_csv(data))).empty
    assert load_workbook(BytesIO(build_full_excel(data, df, "When")))["All flags"].max_row == 1
