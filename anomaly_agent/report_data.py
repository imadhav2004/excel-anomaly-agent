"""Everything a report needs, collected once as plain data.

The PDF, the Excel file and the CSV files are all built from this one dictionary, so the three
formats can never disagree with each other (or with the dashboard).
"""
from datetime import datetime

from anomaly_agent import insights
from anomaly_agent.detection.engine import METHODS
from anomaly_agent.forecasting import ForecastError, forecast_metric
from anomaly_agent.report import describe_change

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
DISCLAIMER = (
    "These are statistical alerts, not confirmed business problems. Forecasts assume the future behaves "
    "like the past. AI text, when present, is a possibility and not a fact. Please check the data before acting."
)
METHOD_NOTES = [
    "Six detection methods vote on every period: percent change, z-score, IQR box plot, rolling average, "
    "seasonal comparison and Isolation Forest. 'Agreement' is how many methods flagged the period.",
    "Severity comes from the strength of the signal: HIGH 2.0 or more, MEDIUM 1.5 or more, otherwise LOW.",
    "Forecasts use exponential smoothing (statsmodels ETS) with a 95% range. The accuracy grade comes from "
    "hiding the newest periods, forecasting them and comparing with what really happened.",
]


def safe_text(value):
    """Spreadsheet programs run text that starts with = + - or @ as a formula. A column name or note that
    comes from an uploaded file must never do that, so a harmless ' is put in front."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def cleaned_csv(df):
    """The cleaned table as CSV bytes, with column names made safe for spreadsheet programs."""
    return df.rename(columns=safe_text).to_csv(index=False).encode("utf-8")


def fmt(value):
    if value is None:
        return "n/a"
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.2f}"


def collect_report_data(
    df, date_column, metrics, summary, anomalies, explanations, source_name, period,
    clean_log=(), horizon=3, forecaster=None, ai_summary=None, created=None,
):
    """`forecaster(df, date_column, metric, horizon)` defaults to forecast_metric (the page passes a cached one).
    `ai_summary` is optional text the user already generated on the AI assistant page."""
    forecaster = forecaster or forecast_metric
    facts = insights.build_facts(df, date_column, metrics, summary, anomalies, source_name, period)
    dates = df[date_column]

    latest = []
    for a in sorted(anomalies, key=lambda a: SEVERITY_ORDER[a["severity"]]):
        note = explanations.get(a["metric"]) or {}
        latest.append({
            "metric": a["metric"], "severity": a["severity"], "direction": a["direction"],
            "change": describe_change(a), "previous": a["previous"], "latest": a["latest"],
            "agreement": f"{a['votes']} of {a['methods_run']}",
            "note": note.get("text", ""), "note_source": note.get("source", "rules"),
        })

    scan = [
        {
            "period": r["period"], "period_label": r["period"].strftime("%b %Y"), "metric": r["metric"],
            "severity": r["severity"], "direction": r["direction"], "actual": r["actual"], "expected": r["expected"],
            "deviation_pct": r["deviation_pct"], "agreement": f"{r['votes']} of {r['methods_run']}",
            "methods": ", ".join(METHODS[m].label for m in r["methods"]), "explanation": r["explanation"],
        }
        for r in sorted(summary, key=lambda r: (-r["period"].value, SEVERITY_ORDER[r["severity"]]))
    ]

    flagged_at = {}
    for r in summary:
        flagged_at.setdefault(r["metric"], set()).add(r["period"])
    series = {}
    for metric in metrics:
        values = df[metric].tolist()
        series[metric] = {
            "dates": list(dates),
            "values": [None if v != v else float(v) for v in values],  # NaN -> None
            "flagged": [i for i, d in enumerate(dates) if d in flagged_at.get(metric, ())],
        }

    forecasts = []
    for metric in metrics:
        try:
            fc = forecaster(df, date_column, metric, horizon)
        except ForecastError as error:
            forecasts.append({"metric": metric, "error": str(error)})
            continue
        forecasts.append({
            "metric": metric, "model": fc["model"], "grade": fc["grade"], "verdict": fc["verdict"],
            "mape": fc["test"]["mape"], "naive_mape": fc["test"]["naive_mape"],
            "last_actual": float(fc["history"].iloc[-1]),
            "rows": [
                {"period": d, "period_label": d.strftime("%b %Y"), "forecast": float(v), "lower": float(lo), "upper": float(hi)}
                for d, v, lo, hi in zip(fc["dates"], fc["forecast"], fc["lower"], fc["upper"])
            ],
        })

    return {
        "title": "Excel Anomaly Agent report",
        "file": source_name,
        "period": period,
        "created": created or datetime.now(),
        "date_range": f"{dates.min():%b %Y} to {dates.max():%b %Y}",
        "kpis": [
            ("Rows analysed", f"{len(df):,}"),
            ("Metrics", str(len(metrics))),
            ("Flagged in latest period", str(len(latest))),
            ("HIGH flags in whole file", str(sum(1 for r in summary if r["severity"] == "HIGH"))),
        ],
        "summary_lines": insights.built_in_insights(facts),
        "ai_summary": (ai_summary or "").strip() or None,
        "latest": latest,
        "scan": scan,
        "series": series,
        "forecasts": forecasts,
        "horizon": horizon,
        "clean_log": list(clean_log),
        "method_notes": METHOD_NOTES,
        "disclaimer": DISCLAIMER,
    }


def scan_csv(data):
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "Period": r["period_label"], "Metric": safe_text(r["metric"]), "Severity": r["severity"], "Direction": r["direction"],
                "Actual": r["actual"], "Expected": r["expected"], "Deviation %": None if r["deviation_pct"] is None else round(r["deviation_pct"] * 100, 1),
                "Agreement": r["agreement"], "Methods": r["methods"], "Explanation": safe_text(r["explanation"]),
            }
            for r in data["scan"]
        ],
        columns=["Period", "Metric", "Severity", "Direction", "Actual", "Expected", "Deviation %", "Agreement", "Methods", "Explanation"],
    )
    return frame.to_csv(index=False).encode("utf-8")


def forecast_csv(data):
    import pandas as pd

    frame = pd.DataFrame(
        [
            {"Metric": safe_text(f["metric"]), "Period": r["period_label"], "Forecast": round(r["forecast"], 2),
             "Lower 95%": round(r["lower"], 2), "Upper 95%": round(r["upper"], 2), "Accuracy": f["grade"]}
            for f in data["forecasts"] if "rows" in f for r in f["rows"]
        ],
        columns=["Metric", "Period", "Forecast", "Lower 95%", "Upper 95%", "Accuracy"],
    )
    return frame.to_csv(index=False).encode("utf-8")
