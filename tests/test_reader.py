import pandas as pd
import pytest

from anomaly_agent.data.reader import list_sheets, read_table
from anomaly_agent.validator import DataError, check_file


def make_df():
    return pd.DataFrame({" Month ": ["2025-01-01", "2025-02-01"], "Revenue": [100, 200]})


def test_reads_csv_with_commas(tmp_path):
    path = tmp_path / "a.csv"
    make_df().to_csv(path, index=False)
    df = read_table(path)
    assert list(df.columns) == ["Month", "Revenue"]  # the spaces in the name are removed
    assert len(df) == 2


def test_reads_csv_with_semicolons(tmp_path):
    path = tmp_path / "a.csv"
    make_df().to_csv(path, index=False, sep=";")
    assert list(read_table(path).columns) == ["Month", "Revenue"]


def test_reads_csv_with_non_utf8_text(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes("Month,Region\n2025-01-01,Caf\xe9\n".encode("latin-1"))
    assert read_table(path)["Region"][0] == "Café"


def test_lists_and_reads_several_sheets(tmp_path):
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        make_df().to_excel(writer, sheet_name="Jan", index=False)
        pd.DataFrame({"Month": ["2025-03-01"], "Revenue": [300]}).to_excel(
            writer, sheet_name="Mar", index=False
        )
    assert list_sheets(path) == ["Jan", "Mar"]
    assert len(read_table(path, "Jan")) == 2
    assert len(read_table(path, "Mar")) == 1
    assert len(read_table(path)) == 2  # no sheet given: the first sheet


def test_csv_has_one_table(tmp_path):
    path = tmp_path / "a.csv"
    make_df().to_csv(path, index=False)
    assert len(list_sheets(path)) == 1


def test_broken_excel_gives_friendly_error(tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"PK\x03\x04 this is not really a workbook")
    with pytest.raises(DataError):
        list_sheets(path)
    with pytest.raises(DataError):
        read_table(path)


def test_renamed_file_is_rejected(tmp_path):
    fake = tmp_path / "fake.xlsx"
    fake.write_bytes(b"MZ this is really a program")
    with pytest.raises(DataError):
        check_file(fake)


def test_binary_file_named_csv_is_rejected(tmp_path):
    fake = tmp_path / "fake.csv"
    fake.write_bytes(b"abc\x00\x01\x02")
    with pytest.raises(DataError):
        check_file(fake)
