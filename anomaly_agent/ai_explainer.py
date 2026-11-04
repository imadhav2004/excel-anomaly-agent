import json
import logging
import os

from dotenv import load_dotenv

from anomaly_agent.report import CONTEXT, GENERIC, describe_change

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("google_genai").setLevel(logging.WARNING)  # hide the library's routine INFO lines

DEFAULT_MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 20_000  # give up after 20 seconds so the app never hangs


def ai_available():
    return bool(os.getenv("GEMINI_API_KEY"))


def rule_based_explanation(anomaly):
    return CONTEXT.get(anomaly["metric"], GENERIC)[anomaly["direction"]]


def build_prompt(anomalies, period):
    # Only the flagged numbers are sent. The rest of the Excel file stays on your computer.
    lines = []
    for a in anomalies:
        lines.append(
            f"- {a['metric']}: {a['previous']:,.0f} -> {a['latest']:,.0f} "
            f"({describe_change(a)}, severity {a['severity']})"
        )
    metrics_text = "\n".join(lines)
    return (
        f"You are a careful business analyst. These metrics changed unusually in {period}:\n"
        f"{metrics_text}\n\n"
        "For each metric write at most 2 short sentences in plain English: the most likely "
        "reasons (as possibilities, not facts) and one thing to check. Do not invent numbers. "
        "Reply with JSON only: an object whose keys are the exact metric names and whose "
        "values are the explanation text."
    )


def ask_gemini(prompt):
    # Imported here so the program still works if the library is not installed
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options=types.HttpOptions(timeout=TIMEOUT_MS),
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text


def parse_explanations(reply):
    start = reply.find("{")
    end = reply.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the AI reply")

    data = json.loads(reply[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("the AI reply is not a JSON object")

    return {str(k): v.strip() for k, v in data.items() if isinstance(v, str) and v.strip()}


def get_explanations(anomalies, period, use_ai=True):
    """Return {metric: {"text": ..., "source": "AI" or "rules"}}. Never fails."""
    result = {
        a["metric"]: {"text": rule_based_explanation(a), "source": "rules"} for a in anomalies
    }

    if not anomalies or not use_ai:
        return result
    if not ai_available():
        logger.info("No GEMINI_API_KEY set. Using built-in explanations.")
        return result

    try:
        reply = ask_gemini(build_prompt(anomalies, period))
        ai_texts = parse_explanations(reply)
    except Exception as error:  # any failure falls back to the built-in sentences
        logger.warning("AI explanation failed (%s). Using built-in explanations.", error)
        return result

    for metric, text in ai_texts.items():
        if metric in result:
            result[metric] = {"text": text[:400], "source": "AI"}
    return result
