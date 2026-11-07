import streamlit as st

from anomaly_agent.detection.engine import METHODS
from anomaly_agent.ui.charts import compare_chart, trend_chart
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.filters import change_vs_previous, indexed, needs_attention
from anomaly_agent.ui.theme import colour_severity, page_header

ctx = get_context()
df, date_column, metrics, summary = ctx["df"], ctx["date_column"], ctx["metrics"], ctx["summary"]

page_header("Overview", f"{ctx['source']} &nbsp;·&nbsp; latest period: <b>{ctx['period']}</b>")

# ---------- Headline numbers ----------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows analysed", len(df), border=True)
k2.metric("Flagged in latest period", len(ctx["anomalies"]), border=True)
k3.metric("Flagged periods (scan)", len(summary), border=True)
k4.metric("HIGH in scan", sum(1 for r in summary if r["severity"] == "HIGH"), border=True)

# ---------- One card per metric ----------
st.subheader("Metrics at a glance")
flagged_now = {a["metric"] for a in ctx["anomalies"]}
per_row = 4
for start in range(0, len(metrics), per_row):
    cols = st.columns(per_row)
    for col, metric in zip(cols, metrics[start : start + per_row]):
        latest, change = change_vs_previous(df[metric])
        label = f"{metric}  ⚠" if metric in flagged_now else metric
        col.metric(
            label,
            "n/a" if latest is None else f"{latest:,.0f}" if abs(latest) >= 100 else f"{latest:,.2f}",
            None if change is None else f"{change:+.1%} vs previous period",
            delta_color="off",
            chart_data=df[metric].tolist(),
            chart_type="line",
            border=True,
        )
if flagged_now:
    st.caption("⚠ = flagged in the latest period. Open the Anomalies page for details.")

# ---------- Trend ----------
st.subheader("Trend")
chosen = st.selectbox("Choose a metric", metrics, key="overview_metric")
st.plotly_chart(trend_chart(df, date_column, chosen, summary), width="stretch")
st.caption("Red circles are periods flagged by the scan. Hover over one to see why.")

# ---------- Needs attention ----------
st.subheader("Needs attention")
top = needs_attention(summary, 5)
if top:
    rows = [
        {
            "Period": r["period"].strftime("%b %Y"),
            "Metric": r["metric"],
            "Severity": r["severity"],
            "Direction": r["direction"],
            "Agreement": f"{r['votes']} of {r['methods_run']} methods",
            "Methods": ", ".join(METHODS[m].label for m in r["methods"]),
        }
        for r in top
    ]
    st.dataframe(colour_severity(rows), hide_index=True)
    st.caption("The five most severe and most recent flagged periods. The Anomalies page has the full list.")
else:
    st.success("No anomalies found in any period.")

# ---------- Compare metrics ----------
if len(metrics) > 1:
    st.subheader("Compare metrics")
    frame = indexed(df, date_column, metrics)
    if frame is not None:
        st.plotly_chart(compare_chart(frame, date_column), width="stretch")
        st.caption("Every metric starts at 100, so metrics of very different size can be compared.")
