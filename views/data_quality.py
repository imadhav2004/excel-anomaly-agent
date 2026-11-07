import streamlit as st

from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import page_header

ctx = get_context()
profile = ctx["profile"]

page_header("Data quality", "What the app found in your file and what it cleaned before analysing.")

q1, q2, q3, q4 = st.columns(4)
q1.metric("Rows in file", profile["rows"], border=True)
q2.metric("Columns", profile["columns"], border=True)
q3.metric("Missing cells", profile["missing_total"], border=True)
q4.metric("Duplicate rows", profile["duplicate_rows"], border=True)

if ctx["tips"]:
    st.subheader("Suggestions")
    for tip in ctx["tips"]:
        st.markdown(f"- {tip}")
else:
    st.success("No data problems found.")

if ctx["clean_log"]:
    st.subheader("What the app did before analysing")
    for line in ctx["clean_log"]:
        st.markdown(f"- {line}")

st.subheader("Column types")
st.dataframe([{"Column": c, "Type": t} for c, t in profile["column_types"].items()], hide_index=True)

with st.expander("Preview the first rows of the original file"):
    st.dataframe(ctx["raw"].head(10), hide_index=True)
with st.expander("Data used for the analysis (after cleaning and filters)"):
    st.dataframe(ctx["df"], hide_index=True)
