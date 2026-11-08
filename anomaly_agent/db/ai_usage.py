"""Rate limit for the AI assistant: every Gemini request of a user is written down, and a user who
asked too often in the last hour has to wait. This protects the free Gemini quota."""
from datetime import timedelta

from sqlalchemy import func, select

from anomaly_agent.db.models import AiCall, utcnow

WINDOW = timedelta(hours=1)
LIMITS = {"question": 10, "insight": 5}  # requests per user per hour


def used_in_last_hour(session, user_id, kind):
    since = utcnow() - WINDOW
    return session.scalar(
        select(func.count()).select_from(AiCall).where(
            AiCall.user_id == user_id, AiCall.kind == kind, AiCall.created_at >= since
        )
    )


def remaining(session, user_id, kind):
    return max(0, LIMITS[kind] - used_in_last_hour(session, user_id, kind))


def minutes_until_free(session, user_id, kind):
    """How long until the oldest request in the window expires (0 if the user may ask now)."""
    if remaining(session, user_id, kind) > 0:
        return 0
    oldest = session.scalar(
        select(func.min(AiCall.created_at)).where(
            AiCall.user_id == user_id, AiCall.kind == kind, AiCall.created_at >= utcnow() - WINDOW
        )
    )
    seconds = (oldest + WINDOW - utcnow()).total_seconds()
    return max(1, int(seconds // 60) + 1)


def record_call(session, user_id, kind):
    """Write the request down. Returns False (and records nothing) if the limit is already reached."""
    if kind not in LIMITS:
        raise ValueError(f"Unknown kind: {kind}")
    if remaining(session, user_id, kind) <= 0:
        return False
    session.add(AiCall(user_id=user_id, kind=kind))
    return True
