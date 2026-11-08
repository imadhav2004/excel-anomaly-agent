from datetime import timedelta

from anomaly_agent.auth import register_user
from anomaly_agent.db import ai_usage, database
from anomaly_agent.db.models import AiCall, utcnow


def two_users(url):
    with database.session_scope(url) as session:
        return (register_user(session, "Asha", "asha@example.com", "Sup3rSecret1"),
                register_user(session, "Ravi", "ravi@example.com", "Sup3rSecret2"))


def test_questions_are_limited_per_hour_and_per_user(url):
    asha, ravi = two_users(url)
    with database.session_scope(url) as session:
        for _ in range(ai_usage.LIMITS["question"]):
            assert ai_usage.record_call(session, asha["id"], "question") is True
        assert ai_usage.record_call(session, asha["id"], "question") is False  # the 11th is refused
        assert ai_usage.remaining(session, asha["id"], "question") == 0
        assert ai_usage.minutes_until_free(session, asha["id"], "question") in range(55, 62)
        assert ai_usage.record_call(session, asha["id"], "insight") is True  # another kind has its own count
        assert ai_usage.remaining(session, ravi["id"], "question") == ai_usage.LIMITS["question"]


def test_old_calls_stop_counting_after_an_hour(url):
    asha, _ = two_users(url)
    with database.session_scope(url) as session:
        for _ in range(ai_usage.LIMITS["insight"]):
            session.add(AiCall(user_id=asha["id"], kind="insight", created_at=utcnow() - timedelta(minutes=61)))
    with database.session_scope(url) as session:
        assert ai_usage.remaining(session, asha["id"], "insight") == ai_usage.LIMITS["insight"]
        assert ai_usage.minutes_until_free(session, asha["id"], "insight") == 0


def test_an_unknown_kind_is_refused_and_deleting_the_user_removes_the_calls(url):
    from anomaly_agent.auth import delete_account
    import pytest

    asha, _ = two_users(url)
    with database.session_scope(url) as session:
        with pytest.raises(ValueError):
            ai_usage.record_call(session, asha["id"], "other")
        ai_usage.record_call(session, asha["id"], "question")
    with database.session_scope(url) as session:
        delete_account(session, asha["id"], "Sup3rSecret1")
    with database.session_scope(url) as session:
        assert session.query(AiCall).count() == 0
