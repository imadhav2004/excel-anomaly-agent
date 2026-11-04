from anomaly_agent.pdf_report import build_pdf_report, clean


def make_anomaly(metric="Revenue"):
    return {
        "metric": metric,
        "direction": "up",
        "latest": 145000.0,
        "previous": 102638.0,
        "pct_change": 0.41,
        "z_score": 15.9,
        "severity": "HIGH",
    }


def test_pdf_is_created():
    explanations = {"Revenue": {"text": "A big order may have landed.", "source": "AI"}}
    data = build_pdf_report([make_anomaly()], explanations, "Oct 2026", 12)
    assert data.startswith(b"%PDF")


def test_pdf_works_with_no_anomalies():
    assert build_pdf_report([], {}, "Oct 2026", 12).startswith(b"%PDF")


def test_fancy_characters_do_not_crash_the_pdf():
    text = "Sales → up – it’s “big” … ₹ 中"
    explanations = {"Revenue": {"text": text, "source": "AI"}}
    assert build_pdf_report([make_anomaly()], explanations, "Oct 2026", 12).startswith(b"%PDF")
    assert clean("→") == "->"
