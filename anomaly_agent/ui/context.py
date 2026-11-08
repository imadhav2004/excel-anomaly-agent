"""The sidebar and the data loading that every page shares.

app.py calls build_context() once per run. It draws the sidebar (upload, cleaning options, filters,
detection settings), loads and cleans the file, runs the detectors and stores everything in
st.session_state. Each page then calls get_context() to read it, so no page repeats this work.
"""
import os
import tempfile
from pathlib import Path

import streamlit as st

from anomaly_agent.ai_explainer import ai_available
from anomaly_agent.data.cleaner import clean_data, fill_gaps, suggest_fixes
from anomaly_agent.data.profiler import find_date_column, profile_data
from anomaly_agent.data.reader import list_sheets, read_table
from anomaly_agent.detection.base import DetectionSettings
from anomaly_agent.detection.engine import METHODS, summarise
from anomaly_agent.latest import latest_anomalies
from anomaly_agent.loader import prepare_dataframe
from anomaly_agent.ui.analysis import cached_scan
from anomaly_agent.ui.auth_ui import current_user
from anomaly_agent.ui.filters import filter_dates
from anomaly_agent.validator import DataError, check_file

SAMPLE_FILE = Path("data/sample_sales.xlsx")
CONTEXT_KEY = "_context"


def is_public_demo():
    """Public demo mode: strangers can use the page, so AI (your quota) and history (shared) are off."""
    return os.getenv("PUBLIC_DEMO", "false").lower() == "true"


def load_secrets():
    # On Streamlit Community Cloud, settings come from "Secrets". Copy them into the environment
    # so the rest of the code can keep using os.getenv.
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "PUBLIC_DEMO", "DATABASE_URL"):
        try:
            if name in st.secrets:
                os.environ.setdefault(name, str(st.secrets[name]))
        except Exception:
            pass  # no secrets file: normal when running on your own computer


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


def get_context():
    """Called by every page. The router (app.py) has always filled it before a page runs."""
    return st.session_state[CONTEXT_KEY]


def build_context():
    """Draw the sidebar, load the data, run the detectors and store the result for the pages."""
    public_demo = is_public_demo()

    st.sidebar.header("Data")
    uploaded = st.sidebar.file_uploader("Upload an Excel or CSV file", type=["xlsx", "xls", "csv"])
    data_box = st.sidebar.container()  # filled in later, once we know the columns of the file

    st.sidebar.header("Filters")
    filter_box = st.sidebar.container()

    st.sidebar.header("Detection")
    pct_threshold = st.sidebar.slider("Flag changes bigger than (%)", 5, 100, 20) / 100
    z_threshold = st.sidebar.slider("Flag z-score above", 1.0, 5.0, 2.0, 0.5)
    with st.sidebar.expander("Advanced detection"):
        chosen_methods = st.multiselect(
            "Methods", list(METHODS), default=list(METHODS), format_func=lambda key: METHODS[key].label
        )
        window = st.slider("Rolling window (periods)", 2, 12, 6)
        iqr_multiplier = st.slider("Box-plot width (IQR multiplier)", 1.0, 3.0, 1.5, 0.5)

    st.sidebar.header("AI")
    if public_demo:
        use_ai = False
        st.sidebar.info("Public demo: AI explanations, history and email are switched off.")
    else:
        use_ai = st.sidebar.checkbox("Use AI explanations (Gemini)", value=ai_available())
        if use_ai and not ai_available():
            st.sidebar.caption("No GEMINI_API_KEY in the .env file, so built-in explanations are used.")
        else:
            st.sidebar.caption("With AI on, only the flagged numbers are sent to Google, not your whole file.")

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
            st.title("Excel Anomaly Agent")
            st.info("Upload an Excel or CSV file in the sidebar to start.")
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
        remove_duplicates = data_box.checkbox("Remove duplicate rows", value=profile["duplicate_rows"] > 0)
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
        st.title("Excel Anomaly Agent")
        st.error(f"Cannot analyse this file: {error}")
        st.stop()

    numeric_columns = [c for c in df.select_dtypes(include="number").columns if c != date_column]
    chosen_metrics = filter_box.multiselect("Metrics to analyse", numeric_columns, default=numeric_columns)
    if not chosen_metrics:
        st.title("Excel Anomaly Agent")
        st.warning("Choose at least one metric in the sidebar.")
        st.stop()
    df = df[[date_column] + chosen_metrics]
    full_rows = len(df)

    first, last = df[date_column].min().to_pydatetime(), df[date_column].max().to_pydatetime()
    if first < last:
        start, end = filter_box.slider(
            "Date range", min_value=first, max_value=last, value=(first, last), format="DD MMM YYYY"
        )
        df = filter_dates(df, date_column, start, end)
    if len(df) < 2:
        st.title("Excel Anomaly Agent")
        st.warning("The chosen date range has fewer than 2 rows. Please choose a wider range.")
        st.stop()

    period = df[date_column].iloc[-1].strftime("%b %Y")
    if chosen_methods:
        settings = DetectionSettings(
            pct_threshold=pct_threshold, z_threshold=z_threshold, iqr_multiplier=iqr_multiplier, window=window
        )
        scan = cached_scan(df, date_column, tuple(chosen_metrics), tuple(chosen_methods), settings)
    else:
        scan = {"anomalies": [], "skipped": [], "ran": {}}

    summary = summarise(scan)
    anomalies = latest_anomalies(df, date_column, summary)  # same scan, so the same severity everywhere

    st.session_state[CONTEXT_KEY] = {
        "public_demo": public_demo,
        "user": current_user(),
        "use_ai": use_ai,
        "df": df,
        "full_rows": full_rows,
        "raw": raw,
        "profile": profile,
        "tips": suggest_fixes(profile),
        "clean_log": clean_log,
        "date_column": date_column,
        "metrics": chosen_metrics,
        "methods": chosen_methods,
        "source": source,
        "source_name": source_name,
        "period": period,
        "anomalies": anomalies,
        "scan": scan,
        "summary": summary,
    }
