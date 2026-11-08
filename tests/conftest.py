import os

import pytest

from anomaly_agent.db import database
from anomaly_agent.db.models import Base


@pytest.fixture(autouse=True)
def no_real_ai_calls(monkeypatch):
    # No test may ever call the real Gemini API, even if your .env has a real key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file and fast password hashing. Nothing touches data/app.db."""
    from anomaly_agent import auth
    from anomaly_agent.db import database

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setattr(auth, "BCRYPT_ROUNDS", 4)
    yield
    database.dispose_engines()


POSTGRES = os.getenv("TEST_POSTGRES_URL")  # an EMPTY test database: its tables are dropped before every test


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
