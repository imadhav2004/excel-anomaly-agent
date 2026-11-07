"""Small pure functions behind the sidebar and table filters (no Streamlit here, so they are easy to test)."""
import pandas as pd

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def filter_dates(df, date_column, start, end):
    """Keep only the rows whose date lies between start and end (both included)."""
    dates = pd.to_datetime(df[date_column])
    keep = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return df[keep].reset_index(drop=True)


def filter_summary(summary, severities, min_votes):
    """Keep scan rows with a chosen severity and at least `min_votes` methods agreeing."""
    return [r for r in summary if r["severity"] in severities and r["votes"] >= min_votes]


def needs_attention(summary, limit=5):
    """The rows to look at first: most severe, then most recent, then most methods agreeing."""
    ranked = sorted(
        summary,
        key=lambda r: (SEVERITY_ORDER.get(r["severity"], 3), -r["period"].toordinal(), -r["votes"]),
    )
    return ranked[:limit]


def change_vs_previous(series):
    """(latest value, change as a fraction of the previous value or None) for one metric."""
    values = series.dropna()
    if len(values) < 2:
        return (float(values.iloc[-1]) if len(values) else None), None
    latest, previous = float(values.iloc[-1]), float(values.iloc[-2])
    return latest, (None if previous == 0 else (latest - previous) / abs(previous))


def indexed(df, date_column, metrics):
    """Every metric rescaled so its first value is 100, to compare metrics of different size."""
    out = {}
    for metric in metrics:
        values = df[metric].dropna()
        if len(values) and values.iloc[0] != 0:
            out[metric] = df[metric] / values.iloc[0] * 100
    return pd.DataFrame(out).assign(**{date_column: df[date_column]}) if out else None
