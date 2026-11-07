"""Cached helpers that run the heavy work once, so moving between pages stays fast."""
import json

import streamlit as st

from anomaly_agent.ai_explainer import ai_available, fetch_ai_explanations, get_explanations, short_reason
from anomaly_agent.detection.engine import run_detection
from anomaly_agent.forecasting import forecast_metric


@st.cache_data(show_spinner="Scanning every period...")
def cached_scan(table, date_column, metrics, methods, settings):
    return run_detection(table, date_column, list(metrics), list(methods), settings)


@st.cache_data(show_spinner="Fitting the forecast model...")
def cached_forecast(table, date_column, metric, horizon):
    return forecast_metric(table, date_column, metric, horizon)


@st.cache_data(ttl=600, show_spinner="Asking Gemini for explanations...")
def cached_ai_texts(anomalies_json, period):
    # Cached for 10 minutes, so moving a slider or a page does not call the AI again.
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
