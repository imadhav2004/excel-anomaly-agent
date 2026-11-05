"""Tests the Streamlit page itself with Streamlit's AppTest.

AppTest cannot click the file-upload box, so we place a test file where the app
looks for its sample data (data/sample_sales.xlsx) and run the page against it.
The upload code path is covered by test_reader.py and test_loader.py.
"""
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from anomaly_agent import ai_explainer

APP_FILE = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def quiet_environment(tmp_path, monkeypatch):
    st.cache_data.clear()  # a result cached by one test must not leak into the next
    monkeypatch.chdir(tmp_path)  # the app looks for data/sample_sales.xlsx in the current folder
    monkeypatch.setenv("PUBLIC_DEMO", "true")  # no AI call, no history file
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / "data").mkdir()
    return tmp_path


def good_table():
    # Fixed numbers (no randomness): Sales jumps in the last month, Refunds stays calm
    return pd.DataFrame(
        {
            "When": pd.date_range("2025-01-01", periods=12, freq="MS"),
            "Sales": [1000 + 10 * (i % 3) for i in range(11)] + [1500],
            "Refunds": [50 + (i % 3) for i in range(12)],
        }
    )


def run_app():
    app = AppTest.from_file(APP_FILE, default_timeout=30)
    app.run()
    return app


def test_date_column_is_found_automatically(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not app.exception
    date_box = [s for s in app.sidebar.selectbox if s.label == "Date column"][0]
    assert date_box.value == "When"
    assert [m.value for m in app.metric if m.label == "Anomalies found"] == ["1"]


def test_messy_file_is_cleaned_and_explained(tmp_path):
    df = good_table()
    df["Refunds"] = df["Refunds"].astype(int).astype(str)
    df.loc[3, "Refunds"] = "unknown"
    df = pd.concat([df, df.iloc[[2]]], ignore_index=True)  # one duplicate row
    df.to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "duplicate" in text
    assert "not numbers" in text
    assert [m.value for m in app.metric if m.label == "Rows analysed"] == ["12"]


def test_choosing_fewer_metrics_changes_the_analysis(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    app.sidebar.multiselect[0].set_value(["Refunds"]).run()
    assert not app.exception
    assert [m.value for m in app.metric if m.label == "Anomalies found"] == ["0"]


def test_a_file_with_no_numbers_shows_a_friendly_error(tmp_path):
    pd.DataFrame({"When": pd.date_range("2025-01-01", periods=6, freq="MS"),
                  "Region": list("abcdef")}).to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not app.exception
    assert any("Cannot analyse this file" in e.value for e in app.error)


def test_public_demo_hides_history_and_ai(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not [c for c in app.sidebar.checkbox if "AI" in c.label]
    assert not [h for h in app.subheader if h.value == "History"]


class BusyError(Exception):
    code = 503


def switch_ai_on(monkeypatch, ask):
    monkeypatch.setenv("PUBLIC_DEMO", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")  # fake: ask_gemini is replaced below
    monkeypatch.setattr(ai_explainer, "ask_gemini", ask)
    # no waiting between retries, and only inside ai_explainer (the global time.sleep stays real)
    monkeypatch.setattr(ai_explainer, "time", SimpleNamespace(sleep=lambda seconds: None))


def test_ai_text_is_labelled_on_the_page(tmp_path, monkeypatch):
    switch_ai_on(monkeypatch, lambda prompt: '{"Sales": "A large order may have landed."}')
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "Sales** (AI suggestion): A large order may have landed." in text
    assert not any("Gemini could not answer" in w.value for w in app.warning)


def test_a_busy_gemini_shows_a_reason_and_builtin_notes(tmp_path, monkeypatch):
    def busy(prompt):
        raise BusyError("high demand")

    switch_ai_on(monkeypatch, busy)
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not app.exception
    assert any("Gemini could not answer" in w.value for w in app.warning)
    assert any("busy" in w.value for w in app.warning)
    assert "built-in note" in " ".join(m.value for m in app.markdown)


def test_a_failed_ai_call_is_not_cached(tmp_path, monkeypatch):
    calls = []

    def recovers_later(prompt):
        calls.append(1)
        if len(calls) <= 3:  # the first page run uses all 3 tries and fails
            raise BusyError("high demand")
        return '{"Sales": "A large order may have landed."}'

    switch_ai_on(monkeypatch, recovers_later)
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert any("Gemini could not answer" in w.value for w in app.warning)  # first run: busy
    app.run()  # second run: Gemini has recovered
    assert not any("Gemini could not answer" in w.value for w in app.warning)
    assert "AI suggestion" in " ".join(m.value for m in app.markdown)
