import pandas as pd


def coerce_numeric_columns(df, skip=()):
    """Turn columns that are mostly numbers (but stored as text) into real numbers.

    A column is converted when at least half of its values are numbers.
    Values that are not numbers (like "n/a") become empty (NaN).
    Returns the new DataFrame and a list of messages about what changed.
    """
    df = df.copy()
    notes = []
    for column in df.columns:
        if column in skip or pd.api.types.is_numeric_dtype(df[column]):
            continue
        converted = pd.to_numeric(df[column], errors="coerce")
        if converted.notna().mean() >= 0.5:
            lost = int(df[column].notna().sum() - converted.notna().sum())
            df[column] = converted
            message = f"Column '{column}' was text and is now numbers."
            if lost:
                message += f" {lost} value(s) were not numbers and became empty."
            notes.append(message)
    return df, notes


def clean_data(df, date_column, remove_duplicates=True):
    """Safe, simple cleaning. Returns (clean DataFrame, list of what was done)."""
    log = []
    df = df.copy()

    before = len(df)
    df = df.dropna(how="all")
    if len(df) < before:
        log.append(f"Removed {before - len(df)} completely empty row(s).")

    if remove_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        if len(df) < before:
            log.append(f"Removed {before - len(df)} duplicate row(s).")

    df, notes = coerce_numeric_columns(df, skip=[date_column])
    log.extend(notes)
    return df.reset_index(drop=True), log


def fill_gaps(df, date_column):
    """Fill empty cells that sit BETWEEN two real values (straight-line interpolation).

    Empty cells at the very start or end are left alone. This matters because
    the newest value is the one we are checking, and we must never invent it.
    Returns (new DataFrame, number of cells filled).
    """
    df = df.copy()
    filled = 0
    for column in df.select_dtypes(include="number").columns:
        if column == date_column:
            continue
        before = int(df[column].isna().sum())
        df[column] = df[column].interpolate(limit_area="inside")
        filled += before - int(df[column].isna().sum())
    return df, filled


def suggest_fixes(profile):
    """Turn a profile (from profile_data) into plain-English suggestions."""
    tips = []
    if profile["date_column"] is None:
        tips.append("No date column was detected. Choose the date column in the sidebar.")
    if profile["empty_rows"]:
        tips.append(f"{profile['empty_rows']} completely empty row(s) will be removed.")
    if profile["duplicate_rows"]:
        tips.append(f"{profile['duplicate_rows']} duplicate row(s) found. Removing them is recommended.")
    if profile["invalid_dates"]:
        tips.append(f"{profile['invalid_dates']} row(s) have a date that cannot be read. They will be dropped.")
    for column, count in profile["text_in_numeric"].items():
        tips.append(f"Column '{column}' has {count} value(s) that are not numbers. They are treated as missing.")
    for column, percent in profile["mostly_empty"].items():
        tips.append(f"Column '{column}' is {percent:.0f}% empty. Consider leaving it out of the analysis.")
    for column, count in profile["missing_by_column"].items():
        if column not in profile["mostly_empty"]:
            tips.append(f"Column '{column}' has {count} missing value(s).")
    return tips
