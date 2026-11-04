import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

DB_PATH = "data/history.db"


def _connect(db_path=None):
    db_path = db_path or DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analyzed_at TEXT,
            source TEXT,
            period TEXT,
            rows INTEGER,
            anomaly_count INTEGER,
            high_count INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER,
            metric TEXT,
            direction TEXT,
            severity TEXT,
            latest REAL,
            previous REAL,
            pct_change REAL,
            z_score REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts_sent (
            source TEXT,
            period TEXT,
            metric TEXT,
            sent_at TEXT,
            PRIMARY KEY (source, period, metric)
        )
        """
    )
    return conn


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def save_analysis(source, period, rows, anomalies, db_path=None):
    high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO analyses (analyzed_at, source, period, rows, anomaly_count, high_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), source, period, rows, len(anomalies), high_count),
        )
        analysis_id = cursor.lastrowid
        for a in anomalies:
            conn.execute(
                "INSERT INTO anomalies (analysis_id, metric, direction, severity, latest, previous, pct_change, z_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    analysis_id,
                    a["metric"],
                    a["direction"],
                    a["severity"],
                    a["latest"],
                    a["previous"],
                    a["pct_change"],
                    a["z_score"],
                ),
            )
    return analysis_id


def get_history(limit=50, db_path=None):
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT analyzed_at, source, period, rows, anomaly_count, high_count "
            "FROM analyses ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    names = ["Saved at", "Source", "Period", "Rows", "Anomalies", "HIGH"]
    return [dict(zip(names, row)) for row in rows]


def filter_new_anomalies(anomalies, source, period, db_path=None):
    """Return only the anomalies we have NOT already emailed for this file and period."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT metric FROM alerts_sent WHERE source = ? AND period = ?",
            (source, period),
        ).fetchall()
    already_sent = {row[0] for row in rows}
    return [a for a in anomalies if a["metric"] not in already_sent]


def mark_alerted(anomalies, source, period, db_path=None):
    with closing(_connect(db_path)) as conn, conn:
        for a in anomalies:
            conn.execute(
                "INSERT OR IGNORE INTO alerts_sent (source, period, metric, sent_at) VALUES (?, ?, ?, ?)",
                (source, period, a["metric"], _now()),
            )
