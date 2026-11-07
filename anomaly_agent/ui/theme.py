"""Look and feel: page style, chart colours and table colours.

The colours of the page itself (background, text, buttons) come from .streamlit/config.toml,
which has a light and a dark theme. Here we only add a little CSS and share chart colours,
so every page looks the same.
"""
import streamlit as st

BLUE = "#4C8DFF"      # actual values
ORANGE = "#FF8F00"    # forecast
PURPLE = "#8E24AA"    # accuracy check
RED = "#E53935"       # anomalies
SEVERITY_COLOURS = {
    "HIGH": "rgba(229, 57, 53, 0.25)",
    "MEDIUM": "rgba(255, 143, 0, 0.25)",
    "LOW": "rgba(253, 216, 53, 0.22)",
}

CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1250px;}
h1 {font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem;}
h2, h3 {letter-spacing: -0.01em;}
[data-testid="stMetric"] {border-radius: 0.9rem;}
[data-testid="stSidebar"] h2 {font-size: 1.05rem; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.75;}
.page-sub {opacity: 0.7; margin-bottom: 1.2rem;}
</style>
"""


def apply_style():
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title, subtitle=""):
    st.title(title)
    if subtitle:
        st.markdown(f'<div class="page-sub">{subtitle}</div>', unsafe_allow_html=True)


def style_figure(fig, height=380):
    """One chart style for every page: transparent background, light grid, legend on top."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", zeroline=False)
    return fig


def colour_severity(rows, column="Severity"):
    """A pandas Styler that colours the Severity cells. Works on a light and a dark theme."""
    import pandas as pd

    frame = pd.DataFrame(rows)

    def paint(value):
        colour = SEVERITY_COLOURS.get(value)
        return f"background-color: {colour}; font-weight: 600" if colour else ""

    if column in frame.columns and len(frame):
        return frame.style.map(paint, subset=[column]).format(precision=2, thousands=",")
    return frame
