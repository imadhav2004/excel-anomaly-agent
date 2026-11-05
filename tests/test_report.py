from anomaly_agent.report import GENERIC, build_email


def make_anomaly(metric="Revenue", direction="up", pct_change=0.41, severity="HIGH"):
    return {
        "metric": metric,
        "direction": direction,
        "latest": 145000.0,
        "previous": 102638.0,
        "pct_change": pct_change,
        "z_score": 15.9,
        "severity": severity,
    }


def test_email_text_has_metric_and_severity():
    subject, body = build_email([make_anomaly()], "Oct 2026")
    assert "1 HIGH" in subject
    assert "[HIGH] Revenue went up 41%" in body
    assert "Why it matters" in body


def test_unknown_metric_uses_generic_note():
    _, body = build_email([make_anomaly(metric="Mystery")], "Oct 2026")
    assert GENERIC["up"] in body


def test_email_says_alerts_are_not_confirmed():
    _, body = build_email([make_anomaly()], "Oct 2026")
    assert "not confirmed business problems" in body


def test_from_zero_wording():
    _, body = build_email([make_anomaly(pct_change=None)], "Oct 2026")
    assert "went up from zero" in body


def test_sales_and_refunds_have_their_own_notes():
    _, body = build_email(
        [make_anomaly(metric="Sales", direction="down"), make_anomaly(metric="Refunds")],
        "Oct 2026",
    )
    assert "Sales fell sharply" in body
    assert "Refunds rose sharply" in body
    assert GENERIC["down"] not in body
