from pathlib import Path

import streamlit as st

from anomaly_agent.db.analyses import delete_analysis, get_analysis, list_analyses, save_analysis
from anomaly_agent.db.database import DatabaseUnavailable, session_scope
from anomaly_agent.report_data import cleaned_csv, collect_report_data, forecast_csv, scan_csv
from anomaly_agent.report_pdf import build_full_pdf
from anomaly_agent.report_xlsx import build_full_excel
from anomaly_agent.report import anomalies_to_rows
from anomaly_agent.ui.analysis import build_explanations, cached_forecast
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import page_header

ctx = get_context()
df, anomalies, period = ctx["df"], ctx["anomalies"], ctx["period"]

page_header("Reports", f"Download the results for {period}, or save them to history.")
explanations, ai_notice = build_explanations(anomalies, period, ctx["use_ai"])
if ai_notice:
    st.warning(ai_notice)

report_name = f"anomaly_report_{period.replace(' ', '_')}"
st.subheader("Full report")
o1, o2 = st.columns(2)
horizon = o1.selectbox("Forecast length (periods)", [3, 6, 12], key="report_horizon")
ai_summary = st.session_state.get("assistant_summary")
use_summary = o2.checkbox(
    "Include the AI summary from the AI assistant page",
    value=False, key="report_ai_summary", disabled=not (ai_summary and ai_summary[1] == "AI"),
    help="Available after you click 'Write an AI summary' on the AI assistant page.",
)
choice = (ctx["source_name"], period, tuple(ctx["metrics"]), tuple(ctx["methods"]), len(df), horizon, use_summary)

if st.button("Prepare report files", key="prepare_report", type="primary"):
    with st.spinner("Building the PDF, Excel and CSV files (this fits a forecast for every metric)..."):
        data = collect_report_data(
            df, ctx["date_column"], ctx["metrics"], ctx["summary"], anomalies, explanations,
            ctx["source_name"], period, clean_log=ctx["clean_log"], horizon=horizon,
            forecaster=cached_forecast, ai_summary=ai_summary[0] if use_summary else None,
        )
        st.session_state["report_files"] = {
            "choice": choice,
            "pdf": build_full_pdf(data),
            "xlsx": build_full_excel(data, df, ctx["date_column"]),
            "scan": scan_csv(data),
            "forecast": forecast_csv(data),
            "flags": len(data["scan"]),
        }
files = st.session_state.get("report_files")
if files and files["choice"] != choice:
    st.info("The file, filters or options changed since the files were prepared. Click 'Prepare report files' again.")
elif files:
    st.success(f"Ready: {files['flags']} flagged period(s) in the scan.")
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("PDF report", files["pdf"], f"{report_name}.pdf", "application/pdf")
    d2.download_button(
        "Excel report", files["xlsx"], f"{report_name}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    d3.download_button("Scan results (CSV)", files["scan"], f"scan_{report_name}.csv", "text/csv")
    d4.download_button("Forecast (CSV)", files["forecast"], f"forecast_{report_name}.csv", "text/csv")
else:
    st.caption("The PDF and Excel files hold the summary, anomalies, charts, forecasts and notes.")
st.download_button(
    "Download cleaned data (CSV)",
    data=cleaned_csv(df),
    file_name=f"cleaned_{Path(ctx['source_name']).stem}.csv",
    mime="text/csv",
)

if not ctx["public_demo"]:
    user_id = ctx["user"]["id"]
    st.subheader("History")
    try:
        if st.button("Save this analysis to history"):
            with session_scope() as session:
                save_analysis(session, user_id, ctx["source_name"], period, len(df), anomalies)
            st.success("Saved to history.")
        with session_scope() as session:
            history = list_analyses(session, user_id)
        if history:
            st.dataframe(
                [
                    {
                        "Saved at": h["saved_at"].strftime("%Y-%m-%d %H:%M"),
                        "Source": h["source"],
                        "Period": h["period"],
                        "Rows": h["rows"],
                        "Anomalies": h["anomalies"],
                        "HIGH": h["high"],
                    }
                    for h in history
                ],
                hide_index=True,
            )
            labels = {h["id"]: f"{h['saved_at']:%Y-%m-%d %H:%M} | {h['source']} | {h['period']}" for h in history}
            chosen = st.selectbox("Open a saved analysis", list(labels), format_func=labels.get, key="history_pick")
            with session_scope() as session:
                saved = get_analysis(session, user_id, chosen)
            if saved and saved["anomaly_list"]:
                st.dataframe(anomalies_to_rows(saved["anomaly_list"]), hide_index=True)
            elif saved:
                st.caption("That analysis had no anomalies.")
            if st.button("Delete this saved analysis", key="history_delete"):
                with session_scope() as session:
                    delete_analysis(session, user_id, chosen)
                st.rerun()
        else:
            st.caption("No saved analyses yet. Click 'Save this analysis to history'.")
    except DatabaseUnavailable as error:
        st.error(str(error))

st.caption("These are statistical alerts, not confirmed business problems.")
