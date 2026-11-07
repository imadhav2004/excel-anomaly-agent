import streamlit as st

from anomaly_agent.detection.engine import METHODS, group_skipped
from anomaly_agent.report import anomalies_to_rows, build_email
from anomaly_agent.ui.analysis import build_explanations
from anomaly_agent.ui.charts import trend_chart
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.filters import filter_summary
from anomaly_agent.ui.theme import colour_severity, page_header

ctx = get_context()
df, date_column, metrics = ctx["df"], ctx["date_column"], ctx["metrics"]
scan, summary, anomalies, period = ctx["scan"], ctx["summary"], ctx["anomalies"], ctx["period"]

page_header("Anomalies", "Unusual values, found two ways: the newest period, and every period with several methods.")
latest_tab, scan_tab = st.tabs(["Latest period", "Scan all periods"])

# ---------- Tab 1: newest period ----------
with latest_tab:
    explanations, ai_notice = build_explanations(anomalies, period, ctx["use_ai"])
    st.subheader(f"Result for {period}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows analysed", len(df), border=True)
    c2.metric("Anomalies found", len(anomalies), border=True)
    c3.metric("HIGH severity", sum(1 for a in anomalies if a["severity"] == "HIGH"), border=True)

    if anomalies:
        st.dataframe(colour_severity(anomalies_to_rows(anomalies)), hide_index=True)
        st.subheader("Why it matters")
        if ai_notice:
            st.warning(ai_notice)
        for a in anomalies:
            item = explanations[a["metric"]]
            label = "AI suggestion" if item["source"] == "AI" else "built-in note"
            st.markdown(f"**{a['metric']}** ({label}): {item['text']}")
        subject, body = build_email(anomalies, period, explanations)
        with st.expander("Preview the alert email"):
            st.write(f"**Subject:** {subject}")
            st.code(body, language=None)
    else:
        st.success("No anomalies found. No email would be sent.")

# ---------- Tab 2: every period ----------
with scan_tab:
    st.caption(
        "This scan checks every period with several methods and shows how many methods agree. "
        "Choose methods and limits in the sidebar under Detection."
    )
    with st.expander("What each method does"):
        for key in ctx["methods"]:
            st.markdown(f"- **{METHODS[key].label}:** {METHODS[key].description}")

    if not ctx["methods"]:
        st.warning("Choose at least one detection method in the sidebar (Advanced detection).")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("Flagged periods", len(summary), border=True)
        s2.metric("Agreed by 2+ methods", sum(1 for r in summary if r["votes"] >= 2), border=True)
        s3.metric("HIGH in scan", sum(1 for r in summary if r["severity"] == "HIGH"), border=True)

        f1, f2 = st.columns(2)
        severities = f1.multiselect("Show severity", ["HIGH", "MEDIUM", "LOW"], default=["HIGH", "MEDIUM", "LOW"])
        most = max([r["methods_run"] for r in summary], default=1)
        min_votes = f2.slider("At least this many methods agree", 1, max(most, 2), 1)
        shown = filter_summary(summary, severities, min_votes)

        def percent(value):
            return "from zero" if value is None else f"{value:+.0%}"

        if summary:
            st.caption(f"Showing {len(shown)} of {len(summary)} flagged periods.")
            st.dataframe(
                colour_severity(
                    [
                        {
                            "Period": r["period"].strftime("%b %Y"),
                            "Metric": r["metric"],
                            "Severity": r["severity"],
                            "Direction": r["direction"],
                            "Actual": round(r["actual"], 2),
                            "Expected": round(r["expected"], 2),
                            "Deviation": percent(r["deviation_pct"]),
                            "Agreement": f"{r['votes']} of {r['methods_run']} methods",
                            "Methods": ", ".join(METHODS[m].label for m in r["methods"]),
                        }
                        for r in shown
                    ]
                ),
                hide_index=True,
            )
            with st.expander("Why was each one flagged? (every method separately)"):
                st.dataframe(
                    [
                        {
                            "Period": a["period"].strftime("%b %Y"),
                            "Metric": a["metric"],
                            "Method": METHODS[a["method"]].label,
                            "Severity": a["severity"],
                            "Score": round(a["score"], 2),
                            "Explanation": a["explanation"],
                        }
                        for a in scan["anomalies"]
                    ],
                    hide_index=True,
                )
                st.caption("Score 1.0 means just over the limit. 2.0 or more is HIGH.")
        else:
            st.success("No anomalies found in any period with these methods.")

        for item in group_skipped(scan):
            st.caption(
                f"**{METHODS[item['method']].label}** was not run: {item['reason']} ({', '.join(item['metrics'])})."
            )

        st.subheader("Trend with anomalies")
        chosen = st.selectbox("Choose a metric", metrics, key="anomaly_metric")
        st.plotly_chart(trend_chart(df, date_column, chosen, summary), width="stretch")
