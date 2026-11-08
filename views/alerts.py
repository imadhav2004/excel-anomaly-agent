import os

import streamlit as st

from anomaly_agent.alerts import (
    DIRECTIONS,
    SCOPES,
    SEVERITIES,
    RuleError,
    build_alert_email,
    describe_rule,
    evaluate_rules,
)
from anomaly_agent.db.alert_repo import (
    clear_events,
    create_rule,
    delete_rule,
    list_events,
    list_rules,
    mark_emailed,
    record_matches,
    set_rule_active,
)
from anomaly_agent.db.database import DatabaseUnavailable, session_scope
from anomaly_agent.emailer import send_email
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import colour_severity, page_header

ctx = get_context()
user, metrics = ctx["user"], ctx["metrics"]

page_header(
    "Alerts",
    "Write rules for what you want to hear about. Run them on the current file, and every new alert "
    "is saved in your history. The same alert is never created twice.",
)

try:
    with session_scope() as session:
        rules = list_rules(session, user["id"])
except DatabaseUnavailable as error:
    st.error(str(error))
    st.stop()

rules_tab, history_tab = st.tabs(["Rules", "Alert history"])

# ---------- Tab 1: rules ----------
with rules_tab:
    with st.expander("Add a rule", expanded=not rules):
        with st.form("add_rule", clear_on_submit=True):
            name = st.text_input("Rule name", key="rule_name", placeholder="for example: Revenue high alert")
            c1, c2 = st.columns(2)
            metric = c1.selectbox("Metric", ["Any metric"] + metrics, key="rule_metric")
            severity = c2.selectbox("Minimum severity", SEVERITIES, index=2, key="rule_severity")
            c3, c4 = st.columns(2)
            votes = c3.slider("At least this many methods agree", 1, 6, 1, key="rule_votes")
            direction = c4.selectbox(
                "Direction", DIRECTIONS, key="rule_direction",
                format_func={"any": "Up or down", "up": "Only increases", "down": "Only decreases"}.get,
            )
            added = st.form_submit_button("Add rule", key="rule_add")
        if added:
            try:
                with session_scope() as session:
                    create_rule(session, user["id"], name, None if metric == "Any metric" else metric,
                                severity, votes, direction)
            except RuleError as error:
                st.error(str(error))
            except DatabaseUnavailable as error:
                st.error(str(error))
            else:
                st.rerun()

    if not rules:
        st.info("You have no rules yet. Add one above, for example: any metric, HIGH severity, 2 methods agree.")
    for rule in rules:
        with st.container(border=True):
            text, switch, trash = st.columns([6, 1.4, 1.2], vertical_alignment="center")
            text.markdown(f"**{rule['name']}**")
            text.caption(describe_rule(rule))
            active = switch.toggle("Active", value=rule["active"], key=f"rule_active_{rule['id']}")
            if trash.button("Delete", key=f"rule_delete_{rule['id']}"):
                with session_scope() as session:
                    delete_rule(session, user["id"], rule["id"])
                st.rerun()
            if active != rule["active"]:
                with session_scope() as session:
                    set_rule_active(session, user["id"], rule["id"], active)
                st.rerun()

    if rules:
        st.subheader("Run the rules")
        st.caption(
            f"Checks the scan of the current file ({ctx['source_name']}). "
            "Choose how far back an alert may look."
        )
        scope_name = st.selectbox("Check", list(SCOPES), key="alert_scope")
        send_mail = st.checkbox(f"Email me the new alerts at {user['email']}", key="alert_email")
        if send_mail and os.getenv("DRY_RUN", "true").lower() == "true":
            st.caption("Dry run is on in the .env file, so the email is only shown here, not sent.")

        if st.button("Run rules now", key="run_rules"):
            if not ctx["methods"]:
                st.warning("No detection method is chosen. Choose methods in the sidebar (Advanced detection).")
            else:
                active_rules = [r for r in rules if r["active"]]
                dates = list(ctx["df"][ctx["date_column"]])
                matches = evaluate_rules(active_rules, ctx["summary"], dates, SCOPES[scope_name])
                try:
                    with session_scope() as session:
                        new_events, known = record_matches(session, user["id"], ctx["source_name"], matches)
                except DatabaseUnavailable as error:
                    st.error(str(error))
                    st.stop()
                r1, r2, r3 = st.columns(3)
                r1.metric("Rules checked", len(active_rules), border=True)
                r2.metric("New alerts", len(new_events), border=True)
                r3.metric("Already alerted before", known, border=True)
                if not new_events:
                    st.success("Nothing new to report." if known else "No rule matched anything in this file.")
                else:
                    st.dataframe(
                        colour_severity(
                            [
                                {"Period": e["period"], "Metric": e["metric"], "Severity": e["severity"],
                                 "Rule": e["rule_name"], "Message": e["message"]}
                                for e in new_events
                            ]
                        ),
                        hide_index=True,
                    )
                    if send_mail:
                        subject, body = build_alert_email(user["name"], ctx["source_name"], new_events)
                        try:
                            sent = send_email(subject, body, to=user["email"])
                        except (OSError, ValueError) as error:
                            st.error(f"The alerts are saved, but the email could not be sent: {error}")
                        else:
                            if sent:
                                with session_scope() as session:
                                    mark_emailed(session, user["id"], [e["id"] for e in new_events])
                                st.success(f"Email sent to {user['email']}.")
                            else:
                                st.info("Dry run: no email was sent. This is what it would say:")
                                st.code(f"Subject: {subject}\n\n{body}", language=None)

# ---------- Tab 2: history ----------
with history_tab:
    try:
        with session_scope() as session:
            events = list_events(session, user["id"])
    except DatabaseUnavailable as error:
        st.error(str(error))
        events = []
    if not events:
        st.caption("No alerts yet. Add a rule and click 'Run rules now'.")
    else:
        shown_severities = st.multiselect("Show severity", SEVERITIES[::-1], default=SEVERITIES[::-1], key="history_severity")
        shown = [e for e in events if e["severity"] in shown_severities]
        st.caption(f"Showing {len(shown)} of {len(events)} alerts, newest first.")
        st.dataframe(
            colour_severity(
                [
                    {
                        "Saved at": e["created_at"].strftime("%Y-%m-%d %H:%M"),
                        "Period": e["period"],
                        "Metric": e["metric"],
                        "Severity": e["severity"],
                        "Rule": e["rule_name"],
                        "File": e["source"],
                        "Emailed": "yes" if e["emailed"] else "no",
                        "Message": e["message"],
                    }
                    for e in shown
                ]
            ),
            hide_index=True,
        )
        if st.button("Clear alert history", key="clear_events"):
            with session_scope() as session:
                clear_events(session, user["id"])
            st.rerun()
