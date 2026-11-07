"""Saved analyses. Every function takes the user's id and uses it in the query,
so one person can never read, change or delete another person's rows."""
import json

from sqlalchemy import select

from anomaly_agent.db.models import Analysis


def _plain(value):
    # numbers from pandas/numpy are not JSON by default; dates become text
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def save_analysis(session, user_id, source_name, period, rows, anomalies):
    high = sum(1 for a in anomalies if a.get("severity") == "HIGH")
    row = Analysis(
        user_id=user_id,
        source_name=source_name[:255],
        period=period,
        row_count=int(rows),
        anomaly_count=len(anomalies),
        high_count=high,
        anomalies_json=json.dumps(anomalies, default=_plain),
    )
    session.add(row)
    session.flush()
    return row.id


def _as_dict(row):
    return {
        "id": row.id,
        "saved_at": row.created_at,
        "source": row.source_name,
        "period": row.period,
        "rows": row.row_count,
        "anomalies": row.anomaly_count,
        "high": row.high_count,
    }


def list_analyses(session, user_id, limit=100):
    query = (
        select(Analysis)
        .where(Analysis.user_id == user_id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
    )
    return [_as_dict(row) for row in session.scalars(query)]


def get_analysis(session, user_id, analysis_id):
    """One saved analysis with its anomalies, or None if it does not exist or is not this user's."""
    row = session.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id))
    if row is None:
        return None
    return {**_as_dict(row), "anomaly_list": json.loads(row.anomalies_json)}


def delete_analysis(session, user_id, analysis_id):
    row = session.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id))
    if row is None:
        return False
    session.delete(row)
    return True
