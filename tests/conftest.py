import pytest


@pytest.fixture(autouse=True)
def no_real_ai_calls(monkeypatch):
    # No test may ever call the real Gemini API, even if your .env has a real key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
