import pytest


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
