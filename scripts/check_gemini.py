"""Live Gemini check. Run from the project folder:  python scripts/check_gemini.py

This makes ONE real API call using the key in your .env file.
It is NOT part of pytest, so the normal tests never touch the internet.
"""
import os
import sys
from pathlib import Path

# Let this script find the anomaly_agent folder (it lives one level above scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from anomaly_agent.ai_explainer import DEFAULT_MODEL, ask_gemini, build_prompt, parse_explanations

# Fake numbers, only used for this check. No real data is sent.
SAMPLE = [
    {"metric": "Sales", "direction": "down", "previous": 229000.0, "latest": 148000.0,
     "pct_change": -0.354, "z_score": -9.0, "severity": "HIGH"},
    {"metric": "Refunds", "direction": "up", "previous": 39.0, "latest": 95.0,
     "pct_change": 1.436, "z_score": 30.4, "severity": "HIGH"},
]


def show_available_models():
    # Helps when the model name is wrong: ask Google which models this key can use.
    try:
        from google import genai

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        names = [m.name for m in client.models.list() if "gemini" in m.name.lower()]
        print("Models this key can see (first 15):")
        for name in names[:15]:
            print("  ", name)
    except Exception as error:
        print("Could not list models:", type(error).__name__)


def main():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("FAIL: GEMINI_API_KEY is empty. Put your key in the .env file (not .env.example).")
        return 1

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    print(f"Model: {model}")
    print(f"Key found ({len(key)} characters, value hidden)")
    print("Calling Gemini...")

    try:
        reply = ask_gemini(build_prompt(SAMPLE, "Oct 2026"))
    except Exception as error:
        print(f"FAIL: the API call failed: {type(error).__name__}: {str(error)[:300]}")
        show_available_models()
        return 1

    print("\nRaw reply from Gemini:")
    print(reply)

    try:
        explanations = parse_explanations(reply)
    except Exception as error:
        print(f"\nFAIL: Gemini answered, but the reply could not be read: {error}")
        return 1

    print("\nParsed explanations:")
    for metric, text in explanations.items():
        print(f"  {metric}: {text}")

    missing = [a["metric"] for a in SAMPLE if a["metric"] not in explanations]
    if missing:
        print(f"\nWARNING: no explanation came back for: {missing}")
        return 1

    print("\nPASS: real Gemini call worked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
