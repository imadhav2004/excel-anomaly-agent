from pathlib import Path

MAX_FILE_MB = 10
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# The first bytes of a real Excel file. A renamed file will not match.
SIGNATURES = {".xlsx": b"PK\x03\x04", ".xls": b"\xd0\xcf\x11\xe0"}
MIN_ROWS = 4  # latest + previous + at least 2 older values


class DataError(Exception):
    """Raised when the file or its data cannot be analysed."""


def check_file(path):
    file = Path(path)

    if not file.exists():
        raise DataError(f"File not found: {path}")

    if file.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DataError(
            f"Unsupported file type '{file.suffix}'. Use one of: {sorted(ALLOWED_EXTENSIONS)}"
        )

    size_mb = file.stat().st_size / 1024 / 1024
    if size_mb > MAX_FILE_MB:
        raise DataError(f"File is {size_mb:.1f} MB. The limit is {MAX_FILE_MB} MB.")

    check_content(file)


def check_content(file):
    """Make sure the file really is what its name says (a renamed .exe is not a .xlsx)."""
    with open(file, "rb") as handle:
        start = handle.read(2048)

    suffix = file.suffix.lower()
    if suffix in SIGNATURES:
        if not start.startswith(SIGNATURES[suffix]):
            raise DataError(f"This file is not a real {suffix} file. Its content does not match its name.")
    elif b"\x00" in start:  # text files never contain null bytes
        raise DataError("This file is not a real CSV text file.")


def check_data(df, date_column):
    if df.empty:
        raise DataError("The file has no data rows.")

    if len(df) < MIN_ROWS:
        raise DataError(f"Need at least {MIN_ROWS} rows, but the file has {len(df)}.")

    numeric_columns = [
        c for c in df.select_dtypes(include="number").columns if c != date_column
    ]
    if not numeric_columns:
        raise DataError("The file has no numeric columns to analyse.")
