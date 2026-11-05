from pathlib import Path

import pandas as pd

from anomaly_agent.validator import DataError

CSV_ENCODINGS = ("utf-8-sig", "latin-1")  # latin-1 can read any byte, so it is the last try


def list_sheets(path):
    """Names of the sheets in an Excel file. A CSV file has just one table."""
    file = Path(path)
    if file.suffix.lower() == ".csv":
        return ["CSV file"]
    try:
        with pd.ExcelFile(file) as book:
            return list(book.sheet_names)
    except Exception as error:
        raise DataError(f"Could not open the Excel file: {error}") from error


def _read_csv(file):
    for encoding in CSV_ENCODINGS:
        try:
            # sep=None lets pandas work out whether the file uses commas, semicolons or tabs
            return pd.read_csv(file, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DataError("Could not read the text in this CSV file.")


def read_table(path, sheet=None):
    """Read one sheet (or a CSV) into a DataFrame. No cleaning happens here."""
    file = Path(path)
    try:
        if file.suffix.lower() == ".csv":
            df = _read_csv(file)
        else:
            df = pd.read_excel(file, sheet_name=0 if sheet is None else sheet)
    except DataError:
        raise
    except Exception as error:
        raise DataError(f"Could not read the file: {error}") from error

    if df.empty and len(df.columns) == 0:
        raise DataError("The file is empty.")

    # Make every column name a clean string, so the rest of the code can rely on it
    df.columns = [str(name).strip() for name in df.columns]
    return df
