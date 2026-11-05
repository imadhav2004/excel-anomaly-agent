import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from anomaly_agent.detection.base import fmt, make_anomaly

NAME = "isolation_forest"
MIN_ROWS = 20
CUTOFF = 0.65  # score above this = unusual. 0.5 would flag about 30% of normal rows on small data.
SCALE = 0.10   # 0.65 is the limit (score 1.0), 0.70 counts as 1.5 and 0.75 as 2.0 (HIGH)


def detect(table, metrics, settings):
    """Look at all metrics TOGETHER and flag rows that sit far away from all the others.

    An Isolation Forest builds many random trees. A row that is separated from the rest after
    only a few random splits is unusual. The anomaly score runs from 0 to 1, and above 0.65
    is treated as "unusual" (the textbook limit of 0.5 flags about 30% of normal rows when data
    is small).

    Honest limits: it splits one metric at a time, so it finds rows that are extreme across
    several metrics at once. It does not detect a broken relationship between two metrics, and
    on small files it adds little to the single-metric methods. It works better with more rows.
    """
    if len(metrics) < 2:
        return [], "needs at least 2 metrics to compare them together"
    data = table[metrics].astype(float).dropna(axis=1, how="all")  # a column with no numbers is useless
    if data.shape[1] < 2:
        return [], "needs at least 2 metrics that contain numbers"
    metrics = list(data.columns)
    data = data.fillna(data.median())
    if len(data) < MIN_ROWS:
        return [], f"needs at least {MIN_ROWS} rows (the file has {len(data)})"

    forest = IsolationForest(n_estimators=200, random_state=42, contamination="auto")
    forest.fit(data)
    anomaly_score = -forest.score_samples(data)  # between 0 and 1, higher = more unusual

    typical = data.median()
    spread = (data - typical).abs().median() * 1.4826
    spread = spread.where(spread > 0, data.std()).replace(0, np.nan)

    found = []
    for position, (date, value) in enumerate(zip(data.index, anomaly_score)):
        if value <= CUTOFF:
            continue
        row = data.iloc[position]  # by position, so two rows with the same date cannot confuse us
        distance = ((row - typical) / spread).abs().fillna(0)
        driver = distance.idxmax()
        actual = row[driver]
        score = 1 + (value - CUTOFF) / SCALE
        text = (
            f"Taken together, the metrics on this date look unusual (isolation score {value:.2f}, "
            f"above {CUTOFF:.2f} means unusual). Biggest driver: {driver}, {fmt(actual)} against a typical "
            f"{fmt(typical[driver])}."
        )
        found.append(make_anomaly(date, driver, NAME, actual, typical[driver], score, text))
    return found, None
