import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from anomaly_agent.ai_explainer import ai_available, get_explanations
from anomaly_agent.detector import detect_anomalies
from anomaly_agent.exporter import build_excel_report
from anomaly_agent.history import get_history, save_analysis
from anomaly_agent.loader import load_data
from anomaly_agent.pdf_report import build_pdf_report
from anomaly_agent.report import anomalies_to_rows, build_email
from anomaly_agent.validator import DataError

SAMPLE_FILE = Path("data/sample_sales.xlsx")

# On Streamlit Community Cloud, settings come from "Secrets". Copy them into the environment
# so the rest of the code can keep using os.getenv.
for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "PUBLIC_DEMO"):
    try:
        if name in st.secrets:
            os.environ.setdefault(name, str(st.secrets[name]))
    except Exception:
        pass  # no secrets file: normal when running on your own computer

# Public demo mode: strangers can use the page, so AI (your quota) and history (shared) are off
PUBLIC_DEMO = os.getenv("PUBLIC_DEMO", "false").lower() == "true"

st.set_page_config(page_title="Excel Anomaly Agent", layout="wide")
st.title("Excel Anomaly Agent")
st.write(
    "Upload an Excel file. The app compares the latest row with the earlier rows "
    "and flags metrics that changed unusually."
)

# ---------- Sidebar settings ----------
st.sidebar.header("Settings")
date_column = st.sidebar.text_input("Date column name", value="Month")
pct_threshold = st.sidebar.slider("Flag changes bigger than (%)", 5, 100, 20) / 100
z_threshold = st.sidebar.slider("Flag z-score above", 1.0, 5.0, 2.0, 0.5)
if PUBLIC_DEMO:
    use_ai = False
    st.sidebar.info("Public demo: AI explanations, history and email are switched off.")
else:
    use_ai = st.sidebar.checkbox("Use AI explanations (Gemini)", value=ai_available())
    if use_ai and not ai_available():
        st.sidebar.caption("No GEMINI_API_KEY in the .env file, so built-in explanations are used.")
    else:
        st.sidebar.caption("With AI on, only the flagged numbers are sent to Google, not your whole file.")

# ---------- Get the data ----------
uploaded = st.file_uploader("Upload an Excel file (.xlsx or .xls)", type=["xlsx", "xls"])


def read_upload(uploaded_file, date_column):
    # load_data needs a real file on disk, so we save the upload to a temporary folder first
    suffix = Path(uploaded_file.name).suffix
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"upload{suffix}"
        path.write_bytes(uploaded_file.getvalue())
        return load_data(path, date_column)


@st.cache_data(ttl=600, show_spinner="Asking Gemini for explanations...")
def cached_explanations(anomalies_json, period, use_ai):
    # cached, so moving a slider does not call the AI again for the same anomalies
    return get_explanations(json.loads(anomalies_json), period, use_ai)


try:
    if uploaded is not None:
        df = read_upload(uploaded, date_column)
        source = uploaded.name
        source_name = uploaded.name
    elif SAMPLE_FILE.exists():
        df = load_data(SAMPLE_FILE, date_column)
        source = "sample data (upload a file to use your own)"
        source_name = SAMPLE_FILE.name
    else:
        st.info("Upload an Excel file to start.")
        st.stop()
except DataError as error:
    st.error(f"Cannot analyse this file: {error}")
    st.stop()

st.caption(f"Showing: {source}")

# ---------- Run the detector ----------
period = df[date_column].iloc[-1].strftime("%b %Y")
anomalies = detect_anomalies(df, date_column, pct_threshold, z_threshold)
high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")
explanations = cached_explanations(json.dumps(anomalies, sort_keys=True), period, use_ai)

st.subheader(f"Result for {period}")
col1, col2, col3 = st.columns(3)
col1.metric("Rows analysed", len(df))
col2.metric("Anomalies found", len(anomalies))
col3.metric("HIGH severity", high_count)

if anomalies:
    st.dataframe(anomalies_to_rows(anomalies), hide_index=True)

    st.subheader("Why it matters")
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

# ---------- Download and save ----------
left, middle, right = st.columns(3)
report_name = f"anomaly_report_{period.replace(' ', '_')}"
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
if not PUBLIC_DEMO and right.button("Save this analysis to history"):
    save_analysis(source_name, period, len(df), anomalies)
    st.success("Saved to history.")

# ---------- Charts ----------
st.subheader("Trend")
metrics = [c for c in df.select_dtypes(include="number").columns if c != date_column]
chosen = st.selectbox("Choose a metric", metrics)
flagged = [a["metric"] for a in anomalies]
if chosen in flagged:
    st.warning(f"{chosen} is flagged in the latest period.")
st.line_chart(df.set_index(date_column)[chosen])

# ---------- Raw data ----------
with st.expander("Show the data"):
    st.dataframe(df, hide_index=True)

# ---------- History ----------
if not PUBLIC_DEMO:
    st.subheader("History")
    history = get_history()
    if history:
        st.dataframe(history, hide_index=True)
    else:
        st.caption("No saved analyses yet. Click 'Save this analysis to history'.")

st.caption("These are statistical alerts, not confirmed business problems.")
