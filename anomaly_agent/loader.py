import logging

import pandas as pd

from anomaly_agent.data.cleaner import coerce_numeric_columns
from anomaly_agent.data.reader import read_table
from anomaly_agent.validator import DataError, check_data, check_file

logger = logging.getLogger(__name__)


def prepare_dataframe(df, date_column):
    """Turn a raw table into analysis-ready data: real dates, real numbers, sorted, validated."""
    if date_column not in df.columns:
        raise DataError(
            f"Column '{date_column}' not found. Columns in file: {list(df.columns)}"
        )

    df = df.copy()

    # Turn the date column into real dates. Bad values become NaT instead of crashing.
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    bad_dates = df[date_column].isna().sum()
    if bad_dates:
        logger.warning("Dropping %s row(s) with an invalid date.", bad_dates)
        df = df.dropna(subset=[date_column])

    # Fix numbers that were typed as text. Keep a column as text if it is mostly text.
    df, _ = coerce_numeric_columns(df, skip=[date_column])

    df = df.sort_values(date_column).reset_index(drop=True)
    check_data(df, date_column)
    return df


def load_data(path, date_column="Month", sheet_name=None):
    """Read a file from disk and prepare it. Works for .xlsx, .xls and .csv."""
    check_file(path)
    df = read_table(path, sheet_name)
    return prepare_dataframe(df, date_column)
