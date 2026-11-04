import pandas as pd

import main
from anomaly_agent import history


def make_file(tmp_path):
    path = tmp_path / "sales.xlsx"
    pd.DataFrame(
        {
            "Month": pd.date_range("2025-01-01", periods=6, freq="MS"),
            "Revenue": [100, 102, 98, 101, 99, 150],
        }
    ).to_excel(path, index=False)
    return str(path)


def setup(tmp_path, monkeypatch, sends):
    monkeypatch.setattr(main, "FILE_PATH", make_file(tmp_path))
    monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "history.db"))
    calls = []

    def fake_send(subject, body):
        calls.append(subject)
        return sends

    monkeypatch.setattr(main, "send_email", fake_send)
    return calls


def test_email_is_sent_once_for_the_same_period(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, sends=True)
    main.main()
    main.main()
    assert len(calls) == 1


def test_dry_run_does_not_use_up_the_alert(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, sends=False)
    main.main()
    main.main()
    assert len(calls) == 2


def test_every_run_is_saved_to_history(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, sends=True)
    main.main()
    main.main()
    assert len(history.get_history()) == 2
