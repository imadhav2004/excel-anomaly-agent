import numpy as np
import pandas as pd
import pytest

from anomaly_agent.detection.base import DetectionSettings
from anomaly_agent.detection.engine import METHODS, group_skipped, run_detection, summarise


def table(rows=12, spike=True):
    values = {
        "Month": pd.date_range("2025-01-01", periods=rows, freq="MS"),
        "Revenue": [100000 + 1000 * (i % 3) for i in range(rows)],
        "Returns": [60 + (i % 4) for i in range(rows)],
    }
    if spike:
        values["Revenue"][-1] = 145000
        values["Returns"][-1] = 25
    return pd.DataFrame(values)


def methods_for(result, metric):
    return {a["method"] for a in result["anomalies"] if a["metric"] == metric}


def test_the_latest_spike_is_found_by_several_methods():
    result = run_detection(table(), "Month")
    assert {"pct_change", "iqr", "rolling"} <= methods_for(result, "Revenue")


def test_every_period_is_scanned_not_only_the_latest():
    df = table()
    df.loc[3, "Revenue"] = 160000  # a spike in the middle of the history
    periods = {a["period"] for a in run_detection(df, "Month")["anomalies"] if a["metric"] == "Revenue"}
    assert pd.Timestamp("2025-04-01") in periods


def test_calm_data_gives_no_anomalies():
    assert run_detection(table(spike=False), "Month")["anomalies"] == []


def test_methods_that_cannot_run_are_reported_with_a_reason():
    result = run_detection(table(), "Month")  # only 12 rows
    skipped = {(s["method"], s["metric"]): s["reason"] for s in result["skipped"]}
    assert "24 rows" in skipped[("seasonal", "Revenue")]
    assert "20 rows" in skipped[("isolation_forest", "all metrics")]


def test_skipped_methods_with_the_same_reason_are_grouped():
    groups = group_skipped(run_detection(table(), "Month"))
    seasonal_group = [g for g in groups if g["method"] == "seasonal"]
    assert len(seasonal_group) == 1
    assert set(seasonal_group[0]["metrics"]) == {"Revenue", "Returns"}


def test_only_the_chosen_methods_run():
    result = run_detection(table(), "Month", methods=["iqr"])
    assert {a["method"] for a in result["anomalies"]} == {"iqr"}
    assert result["skipped"] == []


def test_only_the_chosen_metrics_are_scanned():
    result = run_detection(table(), "Month", metrics=["Returns"])
    assert {a["metric"] for a in result["anomalies"]} == {"Returns"}


def test_an_unknown_method_is_rejected_clearly():
    with pytest.raises(ValueError):
        run_detection(table(), "Month", methods=["magic"])


def test_all_methods_run_on_a_big_enough_file():
    rng = np.random.default_rng(5)
    n = 48
    df = pd.DataFrame(
        {
            "Month": pd.date_range("2022-01-01", periods=n, freq="MS"),
            "Revenue": 100000 + 8000 * np.sin(2 * np.pi * np.arange(n) / 12) + rng.normal(0, 1200, n),
            "Orders": rng.normal(1200, 40, n),
        }
    )
    df.loc[40, "Revenue"] += 20000
    result = run_detection(df, "Month")
    assert result["skipped"] == []
    assert set(result["ran"]["Revenue"]) == set(METHODS)
    assert pd.Timestamp("2025-05-01") in {a["period"] for a in result["anomalies"]}


def test_two_rows_with_the_same_date_do_not_crash():
    df = pd.concat([table(rows=30), table(rows=30).iloc[[5]]], ignore_index=True)
    result = run_detection(df, "Month")
    assert isinstance(result["anomalies"], list)


def test_a_column_with_no_numbers_does_not_crash_the_forest():
    df = table(rows=30)
    df["Empty"] = np.nan
    result = run_detection(df, "Month", metrics=["Revenue", "Returns", "Empty"], methods=["isolation_forest"])
    assert isinstance(result["anomalies"], list)


# ---------- summarise ----------
def test_summary_counts_how_many_methods_agree():
    result = run_detection(table(), "Month")
    rows = summarise(result)
    revenue = [r for r in rows if r["metric"] == "Revenue" and r["period"] == pd.Timestamp("2025-12-01")][0]
    assert revenue["votes"] >= 3
    assert revenue["methods_run"] == 4  # four methods could run on 12 rows
    assert revenue["severity"] == "HIGH"
    assert revenue["direction"] == "up"


def test_summary_is_newest_first_and_has_an_explanation():
    rows = summarise(run_detection(table(), "Month"))
    periods = [r["period"] for r in rows]
    assert periods == sorted(periods, reverse=True)
    assert all(r["explanation"] for r in rows)


def test_summary_has_one_row_per_period_and_metric():
    rows = summarise(run_detection(table(), "Month"))
    keys = [(r["period"], r["metric"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_settings_change_what_is_flagged():
    strict = DetectionSettings(pct_threshold=0.80)
    loose = DetectionSettings(pct_threshold=0.05)
    few = run_detection(table(), "Month", methods=["pct_change"], settings=strict)["anomalies"]
    many = run_detection(table(), "Month", methods=["pct_change"], settings=loose)["anomalies"]
    assert len(many) > len(few)
