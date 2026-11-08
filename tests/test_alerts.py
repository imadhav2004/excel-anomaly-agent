import pandas as pd
import pytest

from anomaly_agent import alerts
from anomaly_agent.alerts import (
    RuleError, alert_message, build_alert_email, clean_rule, describe_rule, evaluate_rules, periods_in_scope, rule_matches,
)


def row(period="2026-10-01", metric="Revenue", severity="HIGH", votes=3, direction="up", deviation=0.32):
    return {"period": pd.Timestamp(period), "metric": metric, "severity": severity, "votes": votes,
            "methods_run": 6, "direction": direction, "actual": 130.0, "expected": 98.0, "deviation_pct": deviation}


def rule(**changes):
    base = {"id": 1, "name": "R", "metric": None, "min_severity": "HIGH", "min_votes": 1, "direction": "any", "active": True}
    return {**base, **changes}


def test_clean_rule_accepts_good_input_and_tidies_it():
    cleaned = clean_rule("  Revenue   high  ", "Revenue", "HIGH", "2", "up")
    assert cleaned == {"name": "Revenue high", "metric": "Revenue", "min_severity": "HIGH", "min_votes": 2, "direction": "up"}
    assert clean_rule("x", "", "LOW", 1, "any")["metric"] is None
    assert clean_rule("x", None, "LOW", 1, "any")["metric"] is None


@pytest.mark.parametrize(
    "args, message",
    [
        (("", None, "HIGH", 1, "any"), "name"),
        (("x" * 61, None, "HIGH", 1, "any"), "at most 60"),
        (("x", None, "SEVERE", 1, "any"), "minimum severity"),
        (("x", None, "HIGH", 0, "any"), "between 1 and 6"),
        (("x", None, "HIGH", 7, "any"), "between 1 and 6"),
        (("x", None, "HIGH", "many", "any"), "whole number"),
        (("x", None, "HIGH", 1, "sideways"), "direction"),
        (("x", "m" * 101, "HIGH", 1, "any"), "too long"),
    ],
)
def test_clean_rule_refuses_bad_input(args, message):
    with pytest.raises(RuleError, match=message):
        clean_rule(*args)


def test_rule_matches_each_condition():
    assert rule_matches(rule(), row())
    assert not rule_matches(rule(metric="Orders"), row())
    assert rule_matches(rule(metric="Revenue"), row())
    assert not rule_matches(rule(min_severity="HIGH"), row(severity="MEDIUM"))
    assert rule_matches(rule(min_severity="MEDIUM"), row(severity="HIGH"))  # "or worse"
    assert not rule_matches(rule(min_votes=4), row(votes=3))
    assert rule_matches(rule(min_votes=3), row(votes=3))
    assert rule_matches(rule(direction="up"), row(direction="up"))
    assert not rule_matches(rule(direction="down"), row(direction="up"))
    assert not rule_matches(rule(active=False), row())


def test_scope_picks_the_newest_periods():
    dates = pd.date_range("2026-01-01", periods=6, freq="MS")
    assert periods_in_scope(dates, 1) == {pd.Timestamp("2026-06-01")}
    assert periods_in_scope(dates, 3) == set(dates[-3:])
    assert periods_in_scope(dates, None) == set(dates)


def test_evaluate_rules_only_looks_inside_the_scope():
    dates = pd.date_range("2026-01-01", periods=10, freq="MS")
    summary = [row("2026-10-01"), row("2026-08-01"), row("2026-03-01")]
    latest = evaluate_rules([rule()], summary, dates, 1)
    assert [m["row"]["period"].month for m in latest] == [10]
    last3 = evaluate_rules([rule()], summary, dates, 3)
    assert [m["row"]["period"].month for m in last3] == [10, 8]
    assert len(evaluate_rules([rule()], summary, dates, None)) == 3
    assert evaluate_rules([rule(active=False)], summary, dates, None) == []


def test_two_rules_can_match_the_same_row():
    dates = pd.date_range("2026-01-01", periods=10, freq="MS")
    matches = evaluate_rules([rule(id=1), rule(id=2, metric="Revenue")], [row()], dates)
    assert [m["rule"]["id"] for m in matches] == [1, 2]


def test_describe_rule_in_plain_words():
    assert describe_rule(rule()) == "any metric: HIGH or worse, at least 1 method agree"
    text = describe_rule(rule(metric="Revenue", min_votes=3, direction="down", min_severity="LOW"))
    assert text == "Revenue: LOW or worse, at least 3 methods agree, only decreases"


def test_alert_message_has_the_facts():
    text = alert_message("Revenue high", row())
    assert text == "Revenue went up +32% in Oct 2026: HIGH, 3 of 6 methods agree (rule: Revenue high)"
    assert "%" not in alert_message("r", row(deviation=None))  # a change from zero has no percent


def test_alert_email_lists_events_and_caps_the_list():
    events = [{"severity": "HIGH", "message": f"alert {i}"} for i in range(25)]
    subject, body = build_alert_email("Asha", "sales.xlsx", events)
    assert subject == "[Excel Anomaly Agent] 25 new alerts in sales.xlsx"
    assert "Hello Asha," in body and "- [HIGH] alert 0" in body
    assert "alert 24" not in body and "and 5 more" in body
    assert "not confirmed business problems" in body
    assert build_alert_email("A", "f", events[:1])[0].endswith("1 new alert in f")
