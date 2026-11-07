import pandas as pd

from anomaly_agent.ui.filters import change_vs_previous, filter_dates, filter_summary, indexed, needs_attention


def row(period, severity, votes, metric="Sales"):
    return {"period": pd.Timestamp(period), "metric": metric, "severity": severity, "votes": votes}


SUMMARY = [
    row("2025-03-01", "LOW", 1),
    row("2025-05-01", "HIGH", 2),
    row("2025-04-01", "HIGH", 4),
    row("2025-06-01", "MEDIUM", 2),
    row("2025-07-01", "LOW", 3),
]


def test_filter_dates_keeps_both_ends():
    df = pd.DataFrame({"When": pd.date_range("2025-01-01", periods=6, freq="MS"), "V": range(6)})
    out = filter_dates(df, "When", "2025-02-01", "2025-04-01")
    assert list(out["V"]) == [1, 2, 3]
    assert list(out.index) == [0, 1, 2]  # row numbers start again from 0


def test_filter_dates_can_return_nothing():
    df = pd.DataFrame({"When": pd.date_range("2025-01-01", periods=3, freq="MS"), "V": range(3)})
    assert filter_dates(df, "When", "2030-01-01", "2030-02-01").empty


def test_filter_summary_by_severity_and_agreement():
    assert [r["votes"] for r in filter_summary(SUMMARY, ["HIGH"], 1)] == [2, 4]
    assert [r["votes"] for r in filter_summary(SUMMARY, ["HIGH", "LOW", "MEDIUM"], 3)] == [4, 3]
    assert filter_summary(SUMMARY, [], 1) == []


def test_needs_attention_puts_severe_then_recent_then_agreed_first():
    top = needs_attention(SUMMARY, 3)
    assert [(r["severity"], r["period"].month) for r in top] == [("HIGH", 5), ("HIGH", 4), ("MEDIUM", 6)]
    assert len(needs_attention(SUMMARY, 99)) == 5
    assert needs_attention([], 5) == []


def test_change_vs_previous():
    assert change_vs_previous(pd.Series([100.0, 150.0])) == (150.0, 0.5)
    assert change_vs_previous(pd.Series([0.0, 5.0])) == (5.0, None)  # no percent from zero
    assert change_vs_previous(pd.Series([7.0])) == (7.0, None)
    assert change_vs_previous(pd.Series([], dtype=float)) == (None, None)
    assert change_vs_previous(pd.Series([1.0, 2.0, None])) == (2.0, 1.0)  # empty cells are ignored


def test_indexed_starts_every_metric_at_100_and_skips_a_zero_start():
    df = pd.DataFrame({"When": pd.date_range("2025-01-01", periods=3, freq="MS"),
                       "A": [10.0, 20.0, 5.0], "B": [1000.0, 1100.0, 900.0], "C": [0.0, 1.0, 2.0]})
    out = indexed(df, "When", ["A", "B", "C"])
    assert list(out["A"]) == [100.0, 200.0, 50.0]
    assert out["B"].iloc[0] == 100.0
    assert "C" not in out.columns
    assert indexed(df, "When", ["C"]) is None
