import pandas as pd
import pytest

from anomaly_agent.alerts import MAX_RULES, RuleError, evaluate_rules
from anomaly_agent.auth import register_user
from anomaly_agent.db import database
from anomaly_agent.db.alert_repo import (
    clear_events, create_rule, delete_rule, list_events, list_rules, mark_emailed, record_matches, set_rule_active,
)

DATES = list(pd.date_range("2026-01-01", periods=10, freq="MS"))


def row(period="2026-10-01", metric="Revenue", severity="HIGH", votes=3):
    return {"period": pd.Timestamp(period), "metric": metric, "severity": severity, "votes": votes,
            "methods_run": 6, "direction": "up", "actual": 130.0, "expected": 98.0, "deviation_pct": 0.32}


def users(url):
    with database.session_scope(url) as session:
        return (register_user(session, "Asha", "asha@example.com", "Sup3rSecret1"),
                register_user(session, "Ravi", "ravi@example.com", "Sup3rSecret2"))


def make_rule(session, user, name="Any high", metric=None):
    return create_rule(session, user["id"], name, metric, "HIGH", 1, "any")


def test_create_list_toggle_and_delete_rules(url):
    asha, _ = users(url)
    with database.session_scope(url) as session:
        first = make_rule(session, asha)
        second = make_rule(session, asha, "Revenue only", "Revenue")
    with database.session_scope(url) as session:
        rules = list_rules(session, asha["id"])
        assert [r["name"] for r in rules] == ["Any high", "Revenue only"]
        assert rules[1]["metric"] == "Revenue" and rules[0]["metric"] is None
        assert rules[0]["active"] is True
        assert set_rule_active(session, asha["id"], first["id"], False) is True
    with database.session_scope(url) as session:
        assert [r["active"] for r in list_rules(session, asha["id"])] == [False, True]
        assert delete_rule(session, asha["id"], second["id"]) is True
    with database.session_scope(url) as session:
        assert [r["name"] for r in list_rules(session, asha["id"])] == ["Any high"]


def test_a_bad_rule_is_refused_and_the_limit_is_enforced(url):
    asha, _ = users(url)
    with database.session_scope(url) as session:
        with pytest.raises(RuleError, match="name"):
            create_rule(session, asha["id"], "", None, "HIGH", 1, "any")
        for i in range(MAX_RULES):
            make_rule(session, asha, f"rule {i}")
        with pytest.raises(RuleError, match="at most"):
            make_rule(session, asha, "one too many")


def test_one_user_cannot_see_change_or_delete_anothers_rules(url):
    asha, ravi = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha)
    with database.session_scope(url) as session:
        assert list_rules(session, ravi["id"]) == []
        assert set_rule_active(session, ravi["id"], rule["id"], False) is False
        assert delete_rule(session, ravi["id"], rule["id"]) is False
    with database.session_scope(url) as session:
        assert list_rules(session, asha["id"])[0]["active"] is True


def test_alerts_are_recorded_once_however_often_the_rules_run(url):
    asha, _ = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha)
        matches = evaluate_rules([rule], [row(), row(metric="Orders")], DATES)
        new, known = record_matches(session, asha["id"], "sales.xlsx", matches)
        assert (len(new), known) == (2, 0)
        assert new[0]["message"].startswith("Revenue went up")
    with database.session_scope(url) as session:
        new, known = record_matches(session, asha["id"], "sales.xlsx", matches)  # run again
        assert (len(new), known) == (0, 2)
        new, known = record_matches(session, asha["id"], "other.xlsx", matches)  # another file is a new alert
        assert (len(new), known) == (2, 0)
    with database.session_scope(url) as session:
        assert len(list_events(session, asha["id"])) == 4


def test_the_same_match_twice_in_one_run_is_stored_once(url):
    asha, _ = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha)
        match = {"rule": rule, "row": row()}
        new, known = record_matches(session, asha["id"], "f.xlsx", [match, match])
        assert len(new) == 1


def test_alerts_stay_in_the_history_after_their_rule_is_deleted(url):
    asha, _ = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha, "Temporary")
        record_matches(session, asha["id"], "f.xlsx", evaluate_rules([rule], [row()], DATES))
        delete_rule(session, asha["id"], rule["id"])
    with database.session_scope(url) as session:
        events = list_events(session, asha["id"])
        assert len(events) == 1
        assert events[0]["rule_name"] == "Temporary" and events[0]["rule_id"] is None


def test_alert_history_is_private_and_can_be_cleared(url):
    asha, ravi = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha)
        new, _ = record_matches(session, asha["id"], "f.xlsx", evaluate_rules([rule], [row()], DATES))
        mark_emailed(session, ravi["id"], [new[0]["id"]])  # Ravi cannot mark Asha's alert
    with database.session_scope(url) as session:
        assert list_events(session, ravi["id"]) == []
        assert list_events(session, asha["id"])[0]["emailed"] is False
        mark_emailed(session, asha["id"], [new[0]["id"]])
    with database.session_scope(url) as session:
        assert list_events(session, asha["id"])[0]["emailed"] is True
        assert clear_events(session, ravi["id"]) == 0
        assert clear_events(session, asha["id"]) == 1
    with database.session_scope(url) as session:
        assert list_events(session, asha["id"]) == []


def test_deleting_the_user_removes_rules_and_alerts(url):
    from anomaly_agent.auth import delete_account

    asha, _ = users(url)
    with database.session_scope(url) as session:
        rule = make_rule(session, asha)
        record_matches(session, asha["id"], "f.xlsx", evaluate_rules([rule], [row()], DATES))
    with database.session_scope(url) as session:
        delete_account(session, asha["id"], "Sup3rSecret1")
    with database.session_scope(url) as session:
        assert list_rules(session, asha["id"]) == [] and list_events(session, asha["id"]) == []
