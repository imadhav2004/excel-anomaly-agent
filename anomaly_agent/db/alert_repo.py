"""Alert rules and alert events in the database. Every query includes the user id."""
from sqlalchemy import func, select, update

from anomaly_agent import alerts
from anomaly_agent.db.models import AlertEvent, AlertRule


def _rule(row):
    return {
        "id": row.id,
        "name": row.name,
        "metric": row.metric,
        "min_severity": row.min_severity,
        "min_votes": row.min_votes,
        "direction": row.direction,
        "active": row.active,
    }


def _event(row):
    return {
        "id": row.id,
        "rule_id": row.rule_id,
        "rule_name": row.rule_name,
        "source": row.source_name,
        "period": row.period_label,
        "metric": row.metric,
        "severity": row.severity,
        "direction": row.direction,
        "votes": row.votes,
        "methods_run": row.methods_run,
        "actual": row.actual,
        "expected": row.expected,
        "message": row.message,
        "emailed": row.emailed,
        "created_at": row.created_at,
    }


def create_rule(session, user_id, name, metric, min_severity, min_votes, direction):
    cleaned = alerts.clean_rule(name, metric, min_severity, min_votes, direction)
    count = session.scalar(select(func.count()).select_from(AlertRule).where(AlertRule.user_id == user_id))
    if count >= alerts.MAX_RULES:
        raise alerts.RuleError(f"You can have at most {alerts.MAX_RULES} rules. Delete one first.")
    row = AlertRule(user_id=user_id, **cleaned)
    session.add(row)
    session.flush()
    return _rule(row)


def list_rules(session, user_id):
    rows = session.scalars(select(AlertRule).where(AlertRule.user_id == user_id).order_by(AlertRule.id))
    return [_rule(row) for row in rows]


def set_rule_active(session, user_id, rule_id, active):
    row = session.scalar(select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id))
    if row is None:
        return False
    row.active = bool(active)
    return True


def delete_rule(session, user_id, rule_id):
    row = session.scalar(select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id))
    if row is None:
        return False
    # Old alerts stay in the history. We empty rule_id ourselves because SQLite ignores ON DELETE SET NULL.
    session.execute(update(AlertEvent).where(AlertEvent.rule_id == row.id).values(rule_id=None))
    session.delete(row)
    return True


def record_matches(session, user_id, source_name, matches):
    """Store the alerts that are new. Returns (new_events, number_already_known).

    "Already known" means the same rule, file, period and metric was alerted before, so nobody gets
    the same alert twice, however often the rules are run.
    """
    new_events, known = [], 0
    seen = set()
    for match in matches:
        rule, row = match["rule"], match["row"]
        period_key = row["period"].strftime("%Y-%m-%d")
        key = (rule["id"], period_key, row["metric"])
        if key in seen:
            continue
        seen.add(key)
        exists = session.scalar(
            select(AlertEvent.id).where(
                AlertEvent.user_id == user_id,
                AlertEvent.rule_id == rule["id"],
                AlertEvent.source_name == source_name[:255],
                AlertEvent.period_key == period_key,
                AlertEvent.metric == row["metric"],
            )
        )
        if exists is not None:
            known += 1
            continue
        event = AlertEvent(
            user_id=user_id,
            rule_id=rule["id"],
            rule_name=rule["name"],
            source_name=source_name[:255],
            period_key=period_key,
            period_label=row["period"].strftime("%b %Y"),
            metric=row["metric"],
            severity=row["severity"],
            direction=row["direction"],
            votes=row["votes"],
            methods_run=row["methods_run"],
            actual=float(row["actual"]),
            expected=None if row["expected"] is None else float(row["expected"]),
            message=alerts.alert_message(rule["name"], row),
        )
        session.add(event)
        session.flush()
        new_events.append(_event(event))
    return new_events, known


def mark_emailed(session, user_id, event_ids):
    for event_id in event_ids:
        row = session.scalar(select(AlertEvent).where(AlertEvent.id == event_id, AlertEvent.user_id == user_id))
        if row is not None:
            row.emailed = True


def list_events(session, user_id, limit=200):
    query = (
        select(AlertEvent)
        .where(AlertEvent.user_id == user_id)
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
        .limit(limit)
    )
    return [_event(row) for row in session.scalars(query)]


def clear_events(session, user_id):
    rows = session.scalars(select(AlertEvent).where(AlertEvent.user_id == user_id)).all()
    for row in rows:
        session.delete(row)
    return len(rows)
