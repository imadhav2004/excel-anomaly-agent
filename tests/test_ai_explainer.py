import pytest

from anomaly_agent import ai_explainer
from anomaly_agent.ai_explainer import (
    build_prompt,
    get_explanations,
    parse_explanations,
)
from anomaly_agent.report import build_email


def make_anomaly(metric="Revenue", direction="up", severity="HIGH"):
    return {
        "metric": metric,
        "direction": direction,
        "latest": 145000.0,
        "previous": 102638.0,
        "pct_change": 0.41,
        "z_score": 15.9,
        "severity": severity,
    }


def test_without_a_key_built_in_sentences_are_used():
    result = get_explanations([make_anomaly()], "Oct 2026")
    assert result["Revenue"]["source"] == "rules"
    assert "Sales income rose sharply" in result["Revenue"]["text"]


def test_ai_text_is_used_when_the_reply_is_good(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(ai_explainer, "ask_gemini", lambda prompt: '{"Revenue": "A big order may have landed."}')
    result = get_explanations([make_anomaly()], "Oct 2026")
    assert result["Revenue"] == {"text": "A big order may have landed.", "source": "AI"}


def test_metric_missing_from_ai_reply_keeps_built_in_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(ai_explainer, "ask_gemini", lambda prompt: '{"Revenue": "A big order may have landed."}')
    result = get_explanations([make_anomaly(), make_anomaly("Returns", "down")], "Oct 2026")
    assert result["Returns"]["source"] == "rules"


def test_ai_failure_falls_back_to_built_in_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def broken(prompt):
        raise TimeoutError("service down")

    monkeypatch.setattr(ai_explainer, "ask_gemini", broken)
    result = get_explanations([make_anomaly()], "Oct 2026")
    assert result["Revenue"]["source"] == "rules"


def test_garbage_reply_falls_back_to_built_in_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(ai_explainer, "ask_gemini", lambda prompt: "sorry, I cannot help")
    result = get_explanations([make_anomaly()], "Oct 2026")
    assert result["Revenue"]["source"] == "rules"


def test_ai_is_not_called_when_switched_off(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def must_not_run(prompt):
        raise AssertionError("the AI should not be called")

    monkeypatch.setattr(ai_explainer, "ask_gemini", must_not_run)
    result = get_explanations([make_anomaly()], "Oct 2026", use_ai=False)
    assert result["Revenue"]["source"] == "rules"


def test_reply_wrapped_in_code_fences_is_understood():
    reply = '```json\n{"Revenue": "Check promotions."}\n```'
    assert parse_explanations(reply) == {"Revenue": "Check promotions."}


def test_reply_that_is_not_an_object_is_rejected():
    with pytest.raises(ValueError):
        parse_explanations("[1, 2, 3]")


def test_prompt_contains_only_the_flagged_numbers():
    prompt = build_prompt([make_anomaly()], "Oct 2026")
    assert "Revenue" in prompt
    assert "102,638 -> 145,000" in prompt
    assert "Oct 2026" in prompt


def test_email_marks_ai_text_and_says_it_is_not_fact():
    explanations = {"Revenue": {"text": "A big order may have landed.", "source": "AI"}}
    _, body = build_email([make_anomaly()], "Oct 2026", explanations)
    assert "Why it matters (AI suggestion): A big order may have landed." in body
    assert "AI suggestions are possibilities, not facts." in body


def test_email_without_ai_has_no_ai_label():
    _, body = build_email([make_anomaly()], "Oct 2026")
    assert "AI suggestion" not in body


class BusyError(Exception):
    code = 503


def test_a_busy_google_is_tried_again_and_then_works(monkeypatch):
    calls = []

    def flaky(prompt):
        calls.append(1)
        if len(calls) < 3:
            raise BusyError("high demand")
        return '{"Revenue": "A big order may have landed."}'

    monkeypatch.setattr(ai_explainer, "ask_gemini", flaky)
    texts = ai_explainer.fetch_ai_explanations([make_anomaly()], "Oct 2026", wait=0)
    assert texts == {"Revenue": "A big order may have landed."}
    assert len(calls) == 3


def test_it_gives_up_after_three_tries(monkeypatch):
    calls = []

    def always_busy(prompt):
        calls.append(1)
        raise BusyError("high demand")

    monkeypatch.setattr(ai_explainer, "ask_gemini", always_busy)
    with pytest.raises(BusyError):
        ai_explainer.fetch_ai_explanations([make_anomaly()], "Oct 2026", wait=0)
    assert len(calls) == 3


def test_other_errors_are_not_retried(monkeypatch):
    calls = []

    def bad_key(prompt):
        calls.append(1)
        raise PermissionError("bad key")

    monkeypatch.setattr(ai_explainer, "ask_gemini", bad_key)
    with pytest.raises(PermissionError):
        ai_explainer.fetch_ai_explanations([make_anomaly()], "Oct 2026", wait=0)
    assert len(calls) == 1


def test_short_reason_is_readable():
    assert "busy" in ai_explainer.short_reason(BusyError())
    assert ai_explainer.short_reason(TimeoutError()) == "TimeoutError"
