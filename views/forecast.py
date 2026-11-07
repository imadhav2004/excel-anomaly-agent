import pandas as pd
import streamlit as st

from anomaly_agent.forecasting import MAX_HORIZON, MIN_ROWS, ForecastError
from anomaly_agent.ui.analysis import cached_forecast
from anomaly_agent.ui.charts import forecast_chart
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import page_header

ctx = get_context()
df, date_column, metrics = ctx["df"], ctx["date_column"], ctx["metrics"]

page_header(
    "Forecast",
    "Predicts the next periods of one metric. The shaded band is the 95% range of likely values. "
    "The accuracy check hides the newest periods, forecasts them and compares with what really happened.",
)

f1, f2 = st.columns(2)
metric = f1.selectbox("Metric to forecast", metrics, key="forecast_metric")
horizon = f2.slider("How many periods ahead", 1, min(MAX_HORIZON, 12), 6, key="forecast_horizon")

try:
    fc = cached_forecast(df, date_column, metric, horizon)
except ForecastError as error:
    fc = None
    st.info(f"No forecast for {metric}: {error}")

if fc is not None:
    test = fc["test"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Average error (MAPE)", "n/a" if test["mape"] is None else f"{test['mape']:.1%}", border=True)
    m2.metric("Simple guess error", "n/a" if test["naive_mape"] is None else f"{test['naive_mape']:.1%}", border=True)
    m3.metric("Hidden values inside band", f"{test['inside_band']:.0%}", border=True)
    st.caption(f"Model chosen automatically: {fc['model']}.")
    {"good": st.success, "fair": st.info, "poor": st.warning}[fc["grade"]](fc["verdict"])
    if fc["gaps_filled"]:
        st.caption(f"{fc['gaps_filled']} empty period(s) were filled by a straight line before forecasting.")

    st.plotly_chart(forecast_chart(fc), width="stretch")

    table = [
        {
            "Period": d.strftime("%b %Y"),
            "Forecast": round(float(v), 2),
            "Lower (95%)": round(float(lo), 2),
            "Upper (95%)": round(float(hi), 2),
        }
        for d, v, lo, hi in zip(fc["dates"], fc["forecast"], fc["lower"], fc["upper"])
    ]
    st.dataframe(table, hide_index=True)
    st.download_button(
        "Download forecast (CSV)",
        pd.DataFrame(table).to_csv(index=False).encode("utf-8"),
        file_name=f"forecast_{metric}.csv",
        mime="text/csv",
    )
    st.caption(
        f"Needs at least {MIN_ROWS} evenly spaced rows. A yearly pattern is used only when the file holds "
        "two or more full years. A forecast assumes the future behaves like the past."
    )
