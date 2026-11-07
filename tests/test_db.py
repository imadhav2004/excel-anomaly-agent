"""Database tests. They run on SQLite always, and also on PostgreSQL when you set TEST_POSTGRES_URL
(an EMPTY test database: its tables are dropped before every test)."""
import os

import pytest
from sqlalchemy import inspect

from anomaly_agent.auth import register_user
from anomaly_agent.db import database
from anomaly_agent.db.analyses import delete_analysis, get_analysis, list_analyses, save_analysis
from anomaly_agent.db.models import Base

POSTGRES = os.getenv("TEST_POSTGRES_URL")
ANOMALIES = [
    {"metric": "Sales", "direction": "up", "latest": 1500.0, "previous": 1010.0,
     "pct_change": 0.485, "z_score": 5.1, "severity": "HIGH"},
    {"metric": "Refunds", "direction": "down", "latest": 40.0, "previous": 52.0,
     "pct_change": -0.23, "z_score": -2.2, "severity": "LOW"},
]


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not POSTGRES, reason="TEST_POSTGRES_URL not set"))])
def url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"
        return
    target = database.normalise_url(POSTGRES)
    engine = database.get_engine(target)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield target
    Base.metadata.drop_all(engine)


def two_users(url):
    with database.session_scope(url) as session:
        return register_user(session, "Asha", "asha@example.com", "Sup3rSecret1"), register_user(
            session, "Ravi", "ravi@example.com", "Sup3rSecret2"
        )


def test_normalise_url_picks_the_psycopg_driver():
    assert database.normalise_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert database.normalise_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert database.normalise_url("  sqlite:///x.db ") == "sqlite:///x.db"
    assert database.normalise_url("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"


def test_default_database_is_a_sqlite_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "load_dotenv", lambda: None)  # a real .env must not change this test
    assert database.database_url() == "sqlite:///data/app.db"


def test_the_password_is_hidden_in_messages():
    assert "secret" not in database.safe_url("postgresql+psycopg://user:secret@localhost:5432/db")
    assert "***" in database.safe_url("postgresql+psycopg://user:secret@localhost:5432/db")


def test_an_unreachable_database_gives_a_friendly_error_without_the_password():
    with pytest.raises(database.DatabaseUnavailable) as caught:
        database.get_engine("postgresql+psycopg://user:topsecret@127.0.0.1:1/nothing")
    assert "topsecret" not in str(caught.value)
    assert "Cannot connect" in str(caught.value)


def test_tables_are_created_and_creating_twice_is_harmless(url):
    engine = database.get_engine(url)
    Base.metadata.create_all(engine)
    assert {"users", "analyses"} <= set(inspect(engine).get_table_names())


def test_save_list_get_and_delete_an_analysis(url):
    asha, _ = two_users(url)
    with database.session_scope(url) as session:
        first = save_analysis(session, asha["id"], "sales.xlsx", "Oct 2026", 12, ANOMALIES)
        second = save_analysis(session, asha["id"], "other.xlsx", "Nov 2026", 24, [])
    with database.session_scope(url) as session:
        rows = list_analyses(session, asha["id"])
        assert [r["id"] for r in rows] == [second, first]  # newest first
        assert (rows[1]["anomalies"], rows[1]["high"], rows[1]["rows"]) == (2, 1, 12)
        saved = get_analysis(session, asha["id"], first)
        assert saved["anomaly_list"] == ANOMALIES  # comes back exactly as saved
        assert delete_analysis(session, asha["id"], first) is True
    with database.session_scope(url) as session:
        assert [r["id"] for r in list_analyses(session, asha["id"])] == [second]


def test_one_user_can_never_see_or_delete_anothers_analysis(url):
    asha, ravi = two_users(url)
    with database.session_scope(url) as session:
        mine = save_analysis(session, asha["id"], "private.xlsx", "Oct 2026", 12, ANOMALIES)
    with database.session_scope(url) as session:
        assert list_analyses(session, ravi["id"]) == []
        assert get_analysis(session, ravi["id"], mine) is None
        assert delete_analysis(session, ravi["id"], mine) is False
    with database.session_scope(url) as session:  # still there for the owner
        assert get_analysis(session, asha["id"], mine) is not None


def test_numpy_numbers_and_dates_in_anomalies_can_be_saved(url):
    import numpy as np
    import pandas as pd

    asha, _ = two_users(url)
    odd = [{"metric": "Sales", "severity": "LOW", "latest": np.float64(2.5), "when": pd.Timestamp("2025-01-01")}]
    with database.session_scope(url) as session:
        saved_id = save_analysis(session, asha["id"], "f.xlsx", "Jan 2025", 3, odd)
    with database.session_scope(url) as session:
        got = get_analysis(session, asha["id"], saved_id)["anomaly_list"][0]
    assert got["latest"] == 2.5 and got["when"].startswith("2025-01-01")


def test_a_failed_unit_of_work_saves_nothing(url):
    asha, _ = two_users(url)
    with pytest.raises(RuntimeError):
        with database.session_scope(url) as session:
            save_analysis(session, asha["id"], "f.xlsx", "Oct 2026", 12, [])
            raise RuntimeError("something went wrong after saving")
    with database.session_scope(url) as session:
        assert list_analyses(session, asha["id"]) == []
