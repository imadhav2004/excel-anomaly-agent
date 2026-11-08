"""Excel Anomaly Agent: the entry point.

Streamlit runs this file first on every click. It checks the login, draws the sidebar and loads
the data once (anomaly_agent/ui/context.py), then shows the page the user picked from the menu.
The pages live in the views/ folder and only read the shared data.
"""
import streamlit as st

from anomaly_agent.ui.auth_ui import render_account_box, require_login
from anomaly_agent.ui.context import build_context, is_public_demo, load_secrets
from anomaly_agent.ui.theme import apply_style

st.set_page_config(page_title="Excel Anomaly Agent", page_icon=":material/monitoring:", layout="wide")
load_secrets()
apply_style()

public_demo = is_public_demo()
user = require_login(public_demo)  # without a login the page stops here (the public demo has no login)

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/anomalies.py", title="Anomalies", icon=":material/warning:"),
    st.Page("views/forecast.py", title="Forecast", icon=":material/trending_up:"),
    st.Page("views/data_quality.py", title="Data quality", icon=":material/fact_check:"),
    st.Page("views/reports.py", title="Reports", icon=":material/description:"),
]
if not public_demo:
    pages.append(st.Page("views/alerts.py", title="Alerts", icon=":material/notifications:"))
    pages.append(st.Page("views/account.py", title="Account", icon=":material/person:"))
navigation = st.navigation(pages)
render_account_box(user)
build_context()  # sidebar + data; stops here with a message if there is no usable file
navigation.run()
