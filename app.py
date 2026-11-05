import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from anomaly_agent.ai_explainer import ai_available, fetch_ai_explanations, get_explanations, short_reason
from anomaly_agent.data.cleaner import clean_data, fill_gaps, suggest_fixes
from anomaly_agent.data.profiler import find_date_column, profile_data
from anomaly_agent.data.reader import list_sheets, read_table
from anomaly_agent.detector import detect_anomalies
from anomaly_agent.exporter import build_excel_report
from anomaly_agent.history import get_history, save_analysis
from anomaly_agent.loader import prepare_dataframe
from anomaly_agent.pdf_report import build_pdf_report
from anomaly_agent.report import anomalies_to_rows, build_email
from anomaly_agent.validator import DataError, check_file

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
    "Upload an Excel or CSV file. The app checks the data, compares the latest row "
    "with the earlier rows and flags metrics that changed unusually."
)

# ---------- Sidebar settings ----------
st.sidebar.header("Settings")
data_box = st.sidebar.container()  # filled in later, once we know the columns of the file
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
uploaded = st.file_uploader("Upload an Excel or CSV file", type=["xlsx", "xls", "csv"])


def save_upload(name, content, folder):
    # the readers need a real file on disk, so we save the upload to a temporary folder first
    path = Path(folder) / f"upload{Path(name).suffix}"
    path.write_bytes(content)
    check_file(path)  # size, extension and real content checks
    return path


@st.cache_data(show_spinner=False)
def upload_sheets(name, content):
    with tempfile.TemporaryDirectory() as folder:
        return list_sheets(save_upload(name, content, folder))


@st.cache_data(show_spinner="Reading the file...")
def upload_table(name, content, sheet):
    with tempfile.TemporaryDirectory() as folder:
        return read_table(save_upload(name, content, folder), sheet)


@st.cache_data(ttl=600, show_spinner="Asking Gemini for explanations...")
def cached_ai_texts(anomalies_json, period):
    # Cached for 10 minutes, so moving a slider does not call the AI again.
    # An error is never cached, so a failed call is tried again on the next run.
    return fetch_ai_explanations(json.loads(anomalies_json), period)


def build_explanations(anomalies, period, use_ai):
    """Built-in notes first, then replace them with AI text when the AI answers.

    Returns (explanations, notice). The notice explains why AI text is missing.
    """
    result = get_explanations(anomalies, period, use_ai=False)
    notice = None
    if use_ai and ai_available() and anomalies:
        try:
            texts = cached_ai_texts(json.dumps(anomalies, sort_keys=True), period)
        except Exception as error:
            notice = (
                f"Gemini could not answer right now ({short_reason(error)}). "
                "Built-in notes are shown. Reload the page to try again."
            )
        else:
            for metric, text in texts.items():
                if metric in result:
                    result[metric] = {"text": text[:400], "source": "AI"}
    return result, notice


try:
    if uploaded is not None:
        content = uploaded.getvalue()
        sheets = upload_sheets(uploaded.name, content)
        source_name = uploaded.name
        source = uploaded.name
    elif SAMPLE_FILE.exists():
        check_file(SAMPLE_FILE)
        sheets = list_sheets(SAMPLE_FILE)
        source_name = SAMPLE_FILE.name
        source = "sample data (upload a file to use your own)"
    else:
        st.info("Upload an Excel or CSV file to start.")
        st.stop()

    sheet = sheets[0]
    if len(sheets) > 1:
        sheet = data_box.selectbox("Sheet", sheets)
        source += f" (sheet: {sheet})"

    if uploaded is not None:
        raw = upload_table(uploaded.name, content, sheet)
    else:
        raw = read_table(SAMPLE_FILE, sheet)

    # Let the app guess the date column. The user can still change it.
    columns = list(raw.columns)
    guess = find_date_column(raw)
    date_column = data_box.selectbox(
        "Date column", columns, index=columns.index(guess) if guess in columns else 0
    )
    if guess is None:
        data_box.caption("No date column was detected. Please choose it yourself.")

    profile = profile_data(raw, date_column)
    remove_duplicates = data_box.checkbox(
        "Remove duplicate rows", value=profile["duplicate_rows"] > 0
    )
    fill_option = data_box.selectbox(
        "Empty cells between two values",
        ["Leave as they are", "Fill by straight-line estimate"],
    )

    cleaned, clean_log = clean_data(raw, date_column, remove_duplicates)
    df = prepare_dataframe(cleaned, date_column)
    if fill_option != "Leave as they are":
        df, filled = fill_gaps(df, date_column)
        if filled:
            clean_log.append(f"Filled {filled} empty cell(s) with a straight-line estimate.")
except DataError as error:
    st.error(f"Cannot analyse this file: {error}")
    st.stop()

numeric_columns = [c for c in df.select_dtypes(include="number").columns if c != date_column]
chosen_metrics = data_box.multiselect("Metrics to analyse", numeric_columns, default=numeric_columns)
if not chosen_metrics:
    st.warning("Choose at least one metric in the sidebar.")
    st.stop()
df = df[[date_column] + chosen_metrics]

st.caption(f"Showing: {source}")

# ---------- Data quality ----------
tips = suggest_fixes(profile)
with st.expander("Data quality and cleaning", expanded=bool(tips)):
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Rows in file", profile["rows"])
    q2.metric("Columns", profile["columns"])
    q3.metric("Missing cells", profile["missing_total"])
    q4.metric("Duplicate rows", profile["duplicate_rows"])
    if tips:
        st.markdown("**Suggestions**")
        for tip in tips:
            st.markdown(f"- {tip}")
    else:
        st.success("No data problems found.")
    if clean_log:
        st.markdown("**What the app did before analysing**")
        for line in clean_log:
            st.markdown(f"- {line}")
    st.markdown("**Column types**")
    st.dataframe(
        [{"Column": c, "Type": t} for c, t in profile["column_types"].items()], hide_index=True
    )
with st.expander("Preview the first rows of the original file"):
    st.dataframe(raw.head(10), hide_index=True)

# ---------- Run the detector ----------
period = df[date_column].iloc[-1].strftime("%b %Y")
anomalies = detect_anomalies(df, date_column, pct_threshold, z_threshold)
high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")
explanations, ai_notice = build_explanations(anomalies, period, use_ai)

st.subheader(f"Result for {period}")
col1, col2, col3 = st.columns(3)
col1.metric("Rows analysed", len(df))
col2.metric("Anomalies found", len(anomalies))
col3.metric("HIGH severity", high_count)

if anomalies:
    st.dataframe(anomalies_to_rows(anomalies), hide_index=True)

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

# ---------- Download and save ----------
left, middle, third, right = st.columns(4)
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
third.download_button(
    "Download cleaned data (CSV)",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name=f"cleaned_{Path(source_name).stem}.csv",
    mime="text/csv",
)
if not PUBLIC_DEMO and right.button("Save this analysis to history"):
    save_analysis(source_name, period, len(df), anomalies)
    st.success("Saved to history.")

# ---------- Charts ----------
st.subheader("Trend")
chosen = st.selectbox("Choose a metric", chosen_metrics)
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
