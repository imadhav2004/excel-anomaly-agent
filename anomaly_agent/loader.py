import logging

import pandas as pd

from anomaly_agent.validator import DataError, check_data, check_file

logger = logging.getLogger(__name__)


def load_data(path, date_column="Month"):
    check_file(path)
    df = pd.read_excel(path)

    if date_column not in df.columns:
        raise DataError(
            f"Column '{date_column}' not found. Columns in file: {list(df.columns)}"
        )

    # Turn the date column into real dates. Bad values become NaT instead of crashing.
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    bad_dates = df[date_column].isna().sum()
    if bad_dates:
        logger.warning("Dropping %s row(s) with an invalid date.", bad_dates)
        df = df.dropna(subset=[date_column])

    # Fix numbers that were typed as text. Keep a column as text if it is mostly text.
    for column in df.columns:
        if column == date_column:
            continue
        converted = pd.to_numeric(df[column], errors="coerce")
        if converted.notna().mean() >= 0.5:
            df[column] = converted

    df = df.sort_values(date_column).reset_index(drop=True)
    check_data(df, date_column)
    return df
