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
from anomaly_agent.auth import register_user
from anomaly_agent.db.database import session_scope

APP_FILE = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def quiet_environment(tmp_path, monkeypatch):
    st.cache_data.clear()  # a result cached by one test must not leak into the next
    monkeypatch.chdir(tmp_path)  # the app looks for data/sample_sales.xlsx in the current folder
    monkeypatch.setenv("PUBLIC_DEMO", "true")  # no AI call, no history file
    # An empty value, not a deleted one: the app copies keys from .env / Streamlit secrets with setdefault,
    # so a deleted key would come back on a computer that has a real key. An empty key stays "no key".
    monkeypatch.setenv("GEMINI_API_KEY", "")
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


def create_user(email="asha@example.com", name="Asha", password="Sup3rSecret1"):
    """A real user in this test's own database."""
    with session_scope() as session:
        return register_user(session, name, email, password)


def run_app(page=None, user=None):
    """Run the app. `page` is a file name in views/, for example "anomalies"; the default page is Overview.

    `user` is a logged-in user (from create_user). Without one, the app behaves like the public demo
    when PUBLIC_DEMO is true, and shows the login screen when it is false.
    """
    app = AppTest.from_file(APP_FILE, default_timeout=60)
    if user is not None:
        app.session_state["auth_user"] = user
    app.run()
    if page:
        app.switch_page(f"views/{page}.py").run()
    return app


def test_date_column_is_found_automatically(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
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
    app = run_app("data_quality")
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "duplicate" in text
    assert "not numbers" in text
    assert [m.value for m in app.metric if m.label == "Rows in file"] == ["13"]
    overview = run_app()
    assert [m.value for m in overview.metric if m.label == "Rows analysed"] == ["12"]


def test_choosing_fewer_metrics_changes_the_analysis(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
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
    app = run_app("reports")
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
    app = run_app("anomalies", user=create_user())
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "Sales** (AI suggestion): A large order may have landed." in text
    assert not any("Gemini could not answer" in w.value for w in app.warning)


def test_a_busy_gemini_shows_a_reason_and_builtin_notes(tmp_path, monkeypatch):
    def busy(prompt):
        raise BusyError("high demand")

    switch_ai_on(monkeypatch, busy)
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies", user=create_user())
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
    app = run_app("anomalies", user=create_user())
    assert any("Gemini could not answer" in w.value for w in app.warning)  # first run: busy
    app.run()  # second run: Gemini has recovered
    assert not any("Gemini could not answer" in w.value for w in app.warning)
    assert "AI suggestion" in " ".join(m.value for m in app.markdown)


def scan_table(app):
    # the scan table is the dataframe that has both "Period" and "Agreement" columns
    for element in app.dataframe:
        if {"Period", "Agreement"} <= set(element.value.columns):
            return element.value
    return None


def test_scan_section_lists_the_spike_with_agreement(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    assert not app.exception
    table = scan_table(app)
    assert table is not None
    row = table[(table["Metric"] == "Sales") & (table["Period"] == "Dec 2025")].iloc[0]
    assert row["Severity"] == "HIGH"
    assert row["Direction"] == "up"
    assert row["Agreement"].startswith(("2 of", "3 of", "4 of"))


def test_scan_says_which_methods_could_not_run(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    text = " ".join(c.value for c in app.caption)
    assert "Seasonal" in text and "24 rows" in text
    assert "Isolation Forest" in text and "20 rows" in text


def test_choosing_one_method_changes_the_scan(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    methods_box = [m for m in app.sidebar.multiselect if m.label == "Methods"][0]
    methods_box.set_value(["iqr"]).run()
    assert not app.exception
    table = scan_table(app)
    assert set(table["Agreement"]) == {"1 of 1 methods"}


def test_scan_with_no_method_chosen_shows_a_warning(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    [m for m in app.sidebar.multiselect if m.label == "Methods"][0].set_value([]).run()
    assert not app.exception
    assert any("at least one detection method" in w.value for w in app.warning)


def test_forecast_section_shows_model_accuracy_and_table(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("forecast")
    assert not app.exception
    labels = [m.label for m in app.metric]
    assert "Average error (MAPE)" in labels and "Simple guess error" in labels
    assert [s.value for s in app.slider if s.label == "How many periods ahead"] == [6]
    forecast_tables = [d for d in app.dataframe if "Forecast" in d.value.columns]
    assert forecast_tables and len(forecast_tables[0].value) == 6


def test_forecast_horizon_slider_changes_the_table(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("forecast")
    [s for s in app.slider if s.label == "How many periods ahead"][0].set_value(3).run()
    assert not app.exception
    forecast_tables = [d for d in app.dataframe if "Forecast" in d.value.columns]
    assert len(forecast_tables[0].value) == 3


def test_forecast_says_why_when_the_file_is_too_short(tmp_path):
    good_table().head(6).to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("forecast")
    assert not app.exception
    assert any("No forecast for" in i.value and "at least" in i.value for i in app.info)


# ---------- Pages, filters and the new dashboard parts ----------


@pytest.mark.parametrize("page", ["overview", "anomalies", "forecast", "data_quality", "reports"])
def test_every_page_opens_without_an_error(tmp_path, page):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app(page)
    assert not app.exception
    assert len(app.title) == 1


def test_overview_has_one_card_per_metric_and_marks_the_flagged_one(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    labels = [m.label for m in app.metric]
    assert "Sales  \u26a0" in labels  # the spike in the newest month
    assert "Refunds" in labels
    latest_card = [m for m in app.metric if m.label.startswith("Sales")][0]
    assert latest_card.value == "1,500"
    assert "+48.5% vs previous period" in latest_card.delta


def test_overview_lists_what_needs_attention(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    tables = [d.value for d in app.dataframe if "Agreement" in d.value.columns]
    assert tables and tables[0].iloc[0]["Metric"] == "Sales"
    assert tables[0].iloc[0]["Severity"] == "HIGH"


def test_date_range_filter_limits_every_page(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    slider = [s for s in app.sidebar.slider if s.label == "Date range"][0]
    start, end = slider.value
    assert len([m for m in app.metric if m.label == "Rows analysed"]) == 1
    slider.set_value((pd.Timestamp("2025-04-01").to_pydatetime(), end)).run()
    assert not app.exception
    assert [m.value for m in app.metric if m.label == "Rows analysed"] == ["9"]


def test_a_date_range_with_one_row_asks_for_a_wider_range(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    slider = [s for s in app.sidebar.slider if s.label == "Date range"][0]
    _, end = slider.value
    slider.set_value((end, end)).run()
    assert not app.exception
    assert any("fewer than 2 rows" in w.value for w in app.warning)


def test_severity_filter_changes_the_scan_table(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    all_rows = scan_table(app)
    assert "HIGH" in set(all_rows["Severity"])
    box = [m for m in app.multiselect if m.label == "Show severity"][0]
    box.set_value(["LOW"]).run()
    assert not app.exception
    table = scan_table(app)  # None when no LOW row exists, which is also correct
    assert table is None or "HIGH" not in set(table["Severity"])


def test_agreement_slider_hides_rows_with_fewer_methods(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("anomalies")
    slider = [s for s in app.slider if s.label == "At least this many methods agree"][0]
    slider.set_value(2).run()
    assert not app.exception
    table = scan_table(app)
    assert table is not None
    assert all(int(a.split(" of ")[0]) >= 2 for a in table["Agreement"])


def test_data_quality_page_shows_counts_and_column_types(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("data_quality")
    labels = {m.label: m.value for m in app.metric}
    assert labels["Rows in file"] == "12"
    assert labels["Duplicate rows"] == "0"
    assert any("Column" in d.value.columns and "Type" in d.value.columns for d in app.dataframe)


def test_reports_page_offers_the_three_downloads(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("reports")
    assert not app.exception
    downloads = [e for e in app.get("download_button")]
    assert len(downloads) == 3


def test_history_is_shown_on_the_reports_page_when_not_public(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "false")
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app("reports", user=create_user())
    assert not app.exception
    assert [h for h in app.subheader if h.value == "History"]


# ---------- Login, accounts and per-user history ----------


def private_app(monkeypatch, tmp_path, page=None, user=None):
    monkeypatch.setenv("PUBLIC_DEMO", "false")
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    return run_app(page, user=user)


def fill(app, **values):
    for key, value in values.items():
        app.text_input(key=key).set_value(value)
    return app


def test_without_a_login_only_the_login_screen_is_shown(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path)
    assert not app.exception
    assert [t.value for t in app.title] == ["Excel Anomaly Agent"]
    assert not app.metric  # no data page was drawn
    assert app.text_input(key="login_email") is not None


def test_the_public_demo_needs_no_login(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert [t.value for t in app.title] == ["Overview"]
    assert not [b for b in app.sidebar.button if b.key == "logout"]
    assert not any(p for p in app.sidebar.markdown if "Signed in" in p.value)


def test_registering_logs_the_person_in(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path)
    fill(app, register_name="Asha", register_email="Asha@Example.com",
         register_password="Sup3rSecret1", register_again="Sup3rSecret1")
    app.button(key="register_submit").click().run()
    assert not app.exception
    assert [t.value for t in app.title] == ["Overview"]
    assert app.session_state["auth_user"]["email"] == "asha@example.com"
    assert any("asha@example.com" in t.value for t in app.sidebar.text)


def test_registering_with_different_passwords_shows_an_error(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path)
    fill(app, register_name="Asha", register_email="a@example.com",
         register_password="Sup3rSecret1", register_again="Different123")
    app.button(key="register_submit").click().run()
    assert any("not the same" in e.value for e in app.error)
    assert "auth_user" not in app.session_state


def test_logging_in_with_the_right_and_the_wrong_password(tmp_path, monkeypatch):
    create_user()
    app = private_app(monkeypatch, tmp_path)
    fill(app, login_email="asha@example.com", login_password="wrong-Pass1")
    app.button(key="login_submit").click().run()
    assert any("Wrong email or password" in e.value for e in app.error)
    fill(app, login_email="asha@example.com", login_password="Sup3rSecret1")
    app.button(key="login_submit").click().run()
    assert not app.exception
    assert app.session_state["auth_user"]["name"] == "Asha"


def test_log_out_returns_to_the_login_screen(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, user=create_user())
    assert [t.value for t in app.title] == ["Overview"]
    app.sidebar.button(key="logout").click().run()
    assert not app.exception
    assert "auth_user" not in app.session_state
    assert app.text_input(key="login_email") is not None


def test_saved_history_is_private_to_each_user(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "false")
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    asha, ravi = create_user("asha@example.com", "Asha"), create_user("ravi@example.com", "Ravi")
    app = run_app("reports", user=asha)
    [b for b in app.button if b.label == "Save this analysis to history"][0].click().run()
    assert not app.exception
    assert any("Saved to history" in s.value for s in app.success)
    assert any("Source" in d.value.columns and len(d.value) == 1 for d in app.dataframe)
    other = run_app("reports", user=ravi)  # Ravi sees nothing of Asha's
    assert not any("Source" in d.value.columns for d in other.dataframe)
    assert any("No saved analyses yet" in c.value for c in other.caption)


def test_account_page_changes_the_password(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, page="account", user=create_user())
    assert not app.exception
    fill(app, cp_current="Sup3rSecret1", cp_new="N3wSecretPass", cp_again="N3wSecretPass")
    app.button(key="cp_submit").click().run()
    assert any("Password changed" in s.value for s in app.success)
    with session_scope() as session:
        from anomaly_agent.auth import login
        assert login(session, "asha@example.com", "N3wSecretPass")["name"] == "Asha"


def test_account_page_rejects_a_wrong_current_password(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, page="account", user=create_user())
    fill(app, cp_current="not-the-one-1", cp_new="N3wSecretPass", cp_again="N3wSecretPass")
    app.button(key="cp_submit").click().run()
    assert any("current password is wrong" in e.value for e in app.error)


def test_deleting_the_account_removes_the_user_and_logs_out(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, page="account", user=create_user())
    fill(app, da_password="Sup3rSecret1")
    app.checkbox(key="da_sure").check()
    app.button(key="da_submit").click().run()
    assert not app.exception
    assert "auth_user" not in app.session_state
    with session_scope() as session:
        from sqlalchemy import select
        from anomaly_agent.db.models import User
        assert session.scalar(select(User)) is None


def test_the_account_page_does_not_exist_in_the_public_demo(tmp_path):
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    app = run_app()
    assert not any("Account" in str(link) for link in app.sidebar.markdown)


# ---------- Phase 6a: alerts page ----------
def add_rule(app, name="Any high", **picks):
    app.text_input(key="rule_name").set_value(name)
    for key, value in picks.items():
        app.selectbox(key=key).set_value(value)
    app.button(key="rule_add").click().run()
    return app


def test_alerts_page_is_not_registered_in_the_public_demo(tmp_path):
    app = run_app()
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        app.switch_page("views/alerts.py")


def test_a_rule_can_be_added_run_and_run_again_without_duplicates(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, page="alerts", user=create_user())
    assert not app.exception
    add_rule(app, "Any high", rule_severity="LOW")
    assert not app.exception and any("Any high" in m.value for m in app.markdown)
    app.button(key="run_rules").click().run()
    assert not app.exception
    new = [m for m in app.metric if m.label == "New alerts"][0]
    assert new.value == "1"  # only Sales jumped in the latest month
    assert any("Sales" in str(d.value) for d in app.dataframe)
    app.button(key="run_rules").click().run()
    assert [m for m in app.metric if m.label == "New alerts"][0].value == "0"
    assert [m for m in app.metric if m.label == "Already alerted before"][0].value == "1"


def test_dry_run_shows_the_email_text_and_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    app = private_app(monkeypatch, tmp_path, page="alerts", user=create_user())
    add_rule(app, "Any", rule_severity="LOW")
    app.checkbox(key="alert_email").check()
    app.button(key="run_rules").click().run()
    assert any("Dry run" in i.value for i in app.info)
    assert any("Hello Asha" in c.value for c in app.code)


def test_alert_history_is_private_and_can_be_cleared(tmp_path, monkeypatch):
    asha, ravi = create_user("asha@example.com", "Asha"), create_user("ravi@example.com", "Ravi")
    app = private_app(monkeypatch, tmp_path, page="alerts", user=asha)
    add_rule(app, "Any", rule_severity="LOW")
    app.button(key="run_rules").click().run()
    other = run_app("alerts", user=ravi)
    assert not other.exception
    assert not any("Any" == str(getattr(m, "value", "")) for m in other.markdown)
    assert not any("Sales" in str(d.value) for d in other.dataframe)
    app = run_app("alerts", user=asha)
    assert any("Sales" in str(d.value) for d in app.dataframe)
    app.button(key="clear_events").click().run()
    assert not app.exception
    assert not any("Sales" in str(d.value) for d in app.dataframe)


def test_a_rule_can_be_switched_off_and_deleted(tmp_path, monkeypatch):
    app = private_app(monkeypatch, tmp_path, page="alerts", user=create_user())
    add_rule(app, "Temp", rule_severity="LOW")
    rid = [t.key for t in app.toggle if t.key.startswith("rule_active_")][0].split("_")[-1]
    app.toggle(key=f"rule_active_{rid}").set_value(False).run()
    app.button(key="run_rules").click().run()
    assert [m for m in app.metric if m.label == "Rules checked"][0].value == "0"
    app.button(key=f"rule_delete_{rid}").click().run()
    assert not app.exception and not any(t.key.startswith("rule_active_") for t in app.toggle)


# ---------- Phase 6b: AI assistant page ----------
def assistant_app(monkeypatch, tmp_path, user=None, ai=False, reply="Sales rose 48.5% in Dec 2025."):
    from anomaly_agent import insights
    monkeypatch.setenv("PUBLIC_DEMO", "false")
    if ai:
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(insights, "ask_gemini_text", reply if callable(reply) else (lambda prompt: reply))
    good_table().to_excel(tmp_path / "data" / "sample_sales.xlsx", index=False)
    return run_app("assistant", user=user or create_user())


def ask(app, text):
    app.chat_input[0].set_value(text).run()
    return app


def test_assistant_page_is_not_registered_in_the_public_demo(tmp_path):
    app = run_app()
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        app.switch_page("views/assistant.py")


def test_without_ai_the_assistant_answers_from_the_numbers(tmp_path, monkeypatch):
    app = assistant_app(monkeypatch, tmp_path)
    assert not app.exception
    assert any("AI is off" in i.value for i in app.info)
    assert any("12 rows" in m.value for m in app.markdown)  # built-in summary is shown at once
    ask(app, "What happened to Sales?")
    assert not app.exception
    assert any("Sales: latest 1,500" in m.value for m in app.markdown)
    assert any("Built-in answer" in c.value for c in app.caption)


def test_with_ai_the_answer_is_labelled_and_only_computed_facts_were_sent(tmp_path, monkeypatch):
    sent = []
    app = assistant_app(monkeypatch, tmp_path, ai=True, reply=lambda prompt: sent.append(prompt) or "Sales rose 48.5% in Dec 2025.")
    assert any("AI is on" in i.value for i in app.info)
    ask(app, "Why is Sales up?")
    assert not app.exception
    assert any("Sales rose 48.5%" in m.value for m in app.markdown)
    assert any("Written by Gemini" in c.value for c in app.caption)
    assert len(sent) == 1 and '"latest": 1500.0' in sent[0] and "Why is Sales up?" in sent[0]


def test_a_failing_gemini_shows_the_builtin_answer_and_the_reason(tmp_path, monkeypatch):
    def broken(prompt):
        raise ValueError("boom")
    app = assistant_app(monkeypatch, tmp_path, ai=True, reply=broken)
    ask(app, "What about Sales?")
    assert not app.exception
    assert any("Sales: latest" in m.value for m in app.markdown)
    assert any("Gemini could not answer: ValueError" in c.value for c in app.caption)


def test_the_question_limit_stops_the_eleventh_ai_call(tmp_path, monkeypatch):
    from anomaly_agent.db.ai_usage import LIMITS
    calls = []
    app = assistant_app(monkeypatch, tmp_path, ai=True, reply=lambda prompt: calls.append(1) or "ok")
    for i in range(LIMITS["question"] + 1):
        ask(app, f"question {i}")
    assert not app.exception
    assert len(calls) == LIMITS["question"]  # the 11th never reached Gemini
    assert any("Limit reached" in c.value for c in app.caption)


def test_the_summary_button_asks_ai_and_the_conversation_can_be_cleared(tmp_path, monkeypatch):
    app = assistant_app(monkeypatch, tmp_path, ai=True, reply="- Sales is unusual.")
    app.button(key="make_summary").click().run()
    assert any("Sales is unusual" in m.value for m in app.markdown)
    ask(app, "hello")
    app.button(key="clear_chat").click().run()
    assert not app.chat_message
