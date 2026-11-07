"""Plotly charts shared by the pages."""
import plotly.graph_objects as go

from anomaly_agent.ui.theme import BLUE, ORANGE, PURPLE, RED, style_figure


def trend_chart(df, date_column, metric, points):
    """The metric over time, with every flagged period circled.

    `points` are rows from the scan summary (see detection.engine.summarise).
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=df[date_column], y=df[metric], mode="lines+markers", name=metric, line=dict(color=BLUE))
    )
    points = [p for p in points if p["metric"] == metric]
    if points:
        fig.add_trace(
            go.Scatter(
                x=[p["period"] for p in points],
                y=[p["actual"] for p in points],
                mode="markers",
                name="Anomaly",
                marker=dict(size=15, symbol="circle-open", color=RED, line=dict(width=3, color=RED)),
                text=[f"{p['severity']}: {p['votes']} of {p['methods_run']} methods<br>{p['explanation']}" for p in points],
                hoverinfo="text",
            )
        )
    fig = style_figure(fig)
    fig.update_layout(hovermode="closest")
    return fig


def compare_chart(indexed_frame, date_column):
    """All metrics on one chart, each starting at 100."""
    fig = go.Figure()
    for metric in [c for c in indexed_frame.columns if c != date_column]:
        fig.add_trace(go.Scatter(x=indexed_frame[date_column], y=indexed_frame[metric], mode="lines", name=metric))
    fig = style_figure(fig, height=340)
    fig.add_hline(y=100, line_dash="dot", line_color="rgba(128,128,128,0.6)")
    return fig


def forecast_chart(fc):
    """Actual values, the 95% band, the forecast and the accuracy-check line."""
    history, test = fc["history"], fc["test"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history.index, y=history.values, mode="lines", name="Actual", line=dict(color=BLUE)))
    fig.add_trace(
        go.Scatter(
            x=fc["dates"] + fc["dates"][::-1],
            y=list(fc["upper"]) + list(fc["lower"][::-1]),
            mode="lines",
            fill="toself",
            fillcolor="rgba(255, 143, 0, 0.18)",
            line=dict(width=0),
            hoverinfo="skip",
            name="95% band",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[history.index[-1]] + fc["dates"],
            y=[history.values[-1]] + list(fc["forecast"]),
            mode="lines+markers",
            name="Forecast",
            line=dict(dash="dash", color=ORANGE),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=test["dates"],
            y=test["predicted"],
            mode="lines+markers",
            name="Accuracy check (hidden periods)",
            line=dict(dash="dot", color=PURPLE),
        )
    )
    return style_figure(fig, height=400)
