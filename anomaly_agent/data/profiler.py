import warnings

import pandas as pd

DATE_WORDS = ("date", "month", "period", "day", "week", "time", "year")
MOSTLY_EMPTY_PERCENT = 50
DATE_MATCH_SHARE = 0.6  # at least this share of values must look like dates


def _looks_like_dates(series):
    values = series.dropna()
    if values.empty:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pandas warns when it has to guess a date format
        parsed = pd.to_datetime(values.astype(str), errors="coerce")
    return parsed.notna().mean() >= DATE_MATCH_SHARE


def find_date_column(df):
    """Guess which column holds the dates. Returns its name, or None."""
    candidates = []
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            candidates.append(column)
        elif pd.api.types.is_numeric_dtype(series):
            continue  # numbers like 1, 2, 3 would wrongly parse as dates
        elif _looks_like_dates(series):
            candidates.append(column)

    if not candidates:
        return None
    for column in candidates:  # a name like "Month" or "Date" is the best sign
        if any(word in str(column).lower() for word in DATE_WORDS):
            return column
    return candidates[0]


def profile_data(df, date_column="auto"):
    """Check the quality of a raw table. Returns a dictionary of facts."""
    if date_column == "auto":
        date_column = find_date_column(df)

    column_types = {}
    text_in_numeric = {}
    for column in df.columns:
        series = df[column]
        if column == date_column:
            column_types[column] = "date"
        elif pd.api.types.is_numeric_dtype(series):
            column_types[column] = "number"
        else:
            converted = pd.to_numeric(series, errors="coerce")
            if converted.notna().mean() >= 0.5:
                column_types[column] = "number (stored as text)"
                bad = int(series.notna().sum() - converted.notna().sum())
                if bad:
                    text_in_numeric[column] = bad
            else:
                column_types[column] = "text"

    missing = df.isna().sum()
    missing_by_column = {c: int(n) for c, n in missing.items() if n > 0}
    mostly_empty = {}
    for column, count in missing_by_column.items():
        percent = count / len(df) * 100
        if percent >= MOSTLY_EMPTY_PERCENT:
            mostly_empty[column] = percent

    invalid_dates = 0
    if date_column is not None and date_column in df.columns:
        series = df[date_column]
        if not pd.api.types.is_datetime64_any_dtype(series):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(series, errors="coerce")
            invalid_dates = int(parsed.isna().sum() - series.isna().sum())

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "date_column": date_column,
        "column_types": column_types,
        "missing_total": int(missing.sum()),
        "missing_by_column": missing_by_column,
        "mostly_empty": mostly_empty,
        "duplicate_rows": int(df.duplicated().sum()),
        "empty_rows": int(df.isna().all(axis=1).sum()),
        "invalid_dates": invalid_dates,
        "text_in_numeric": text_in_numeric,
    }
