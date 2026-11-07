from pathlib import Path

import streamlit as st

from anomaly_agent.exporter import build_excel_report
from anomaly_agent.history import get_history, save_analysis
from anomaly_agent.pdf_report import build_pdf_report
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
    st.subheader("History")
    if st.button("Save this analysis to history"):
        save_analysis(ctx["source_name"], period, len(df), anomalies)
        st.success("Saved to history.")
    history = get_history()
    if history:
        st.dataframe(history, hide_index=True)
    else:
        st.caption("No saved analyses yet. Click 'Save this analysis to history'.")

st.caption("These are statistical alerts, not confirmed business problems.")
