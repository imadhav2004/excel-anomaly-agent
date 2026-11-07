"""Excel Anomaly Agent: the entry point.

Streamlit runs this file first on every click. It draws the sidebar and loads the data once
(anomaly_agent/ui/context.py), then shows the page the user picked from the menu. The pages
live in the views/ folder and only read the shared data, so no page repeats the loading code.
"""
import streamlit as st

from anomaly_agent.ui.context import build_context, load_secrets
from anomaly_agent.ui.theme import apply_style

st.set_page_config(page_title="Excel Anomaly Agent", page_icon=":material/monitoring:", layout="wide")
load_secrets()
apply_style()

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/anomalies.py", title="Anomalies", icon=":material/warning:"),
    st.Page("views/forecast.py", title="Forecast", icon=":material/trending_up:"),
    st.Page("views/data_quality.py", title="Data quality", icon=":material/fact_check:"),
    st.Page("views/reports.py", title="Reports", icon=":material/description:"),
]
navigation = st.navigation(pages)
build_context()  # sidebar + data; stops here with a message if there is no usable file
navigation.run()
