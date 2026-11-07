from pathlib import Path

import streamlit as st

from anomaly_agent.exporter import build_excel_report
from anomaly_agent.db.analyses import delete_analysis, get_analysis, list_analyses, save_analysis
from anomaly_agent.db.database import DatabaseUnavailable, session_scope
from anomaly_agent.pdf_report import build_pdf_report
from anomaly_agent.report import anomalies_to_rows
from anomaly_agent.ui.analysis import build_explanations
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import page_header

ctx = get_context()
df, anomalies, period = ctx["df"], ctx["anomalies"], ctx["period"]

page_header("Reports", f"Download the results for {period}, or save them to history.")
explanations, ai_notice = build_explanations(anomalies, period, ctx["use_ai"])
if ai_notice:
    st.warning(ai_notice)

report_name = f"anomaly_report_{period.replace(' ', '_')}"
left, middle, right = st.columns(3)
left.download_button(
    "Download Excel report",
    data=build_excel_report(df, anomalies, period),
    file_name=f"{report_name}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
middle.download_button(
    "Download PDF report",
    data=build_pdf_report(anomalies, explanations, period, len(df)),
    file_name=f"{report_name}.pdf",
    mime="application/pdf",
)
right.download_button(
    "Download cleaned data (CSV)",
    data=df.to_csv(index=False).encode("utf-8"),
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
