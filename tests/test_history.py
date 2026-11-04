from anomaly_agent.history import (
    filter_new_anomalies,
    get_history,
    mark_alerted,
    save_analysis,
)


def make_anomaly(metric="Revenue", severity="HIGH"):
    return {
        "metric": metric,
        "direction": "up",
        "latest": 145000.0,
        "previous": 102638.0,
        "pct_change": 0.41,
        "z_score": 15.9,
        "severity": severity,
    }


def test_saved_analysis_can_be_read_back(tmp_path):
    db = tmp_path / "history.db"
    save_analysis("sales.xlsx", "Oct 2026", 12, [make_anomaly(), make_anomaly("Returns", "MEDIUM")], db_path=db)
    history = get_history(db_path=db)
    assert len(history) == 1
    assert history[0]["Period"] == "Oct 2026"
    assert history[0]["Anomalies"] == 2
    assert history[0]["HIGH"] == 1


def test_newest_analysis_comes_first(tmp_path):
    db = tmp_path / "history.db"
    save_analysis("a.xlsx", "Sep 2026", 12, [], db_path=db)
    save_analysis("a.xlsx", "Oct 2026", 12, [], db_path=db)
    assert get_history(db_path=db)[0]["Period"] == "Oct 2026"


def test_new_anomalies_are_kept_before_alerting(tmp_path):
    db = tmp_path / "history.db"
    anomalies = [make_anomaly()]
    assert filter_new_anomalies(anomalies, "sales.xlsx", "Oct 2026", db_path=db) == anomalies


def test_already_alerted_anomalies_are_removed(tmp_path):
    db = tmp_path / "history.db"
    anomalies = [make_anomaly("Revenue"), make_anomaly("Returns")]
    mark_alerted([anomalies[0]], "sales.xlsx", "Oct 2026", db_path=db)
    result = filter_new_anomalies(anomalies, "sales.xlsx", "Oct 2026", db_path=db)
    assert [a["metric"] for a in result] == ["Returns"]


def test_other_period_is_not_affected(tmp_path):
    db = tmp_path / "history.db"
    anomalies = [make_anomaly()]
    mark_alerted(anomalies, "sales.xlsx", "Oct 2026", db_path=db)
    assert filter_new_anomalies(anomalies, "sales.xlsx", "Nov 2026", db_path=db) == anomalies
