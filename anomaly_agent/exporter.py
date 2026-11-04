from io import BytesIO

import pandas as pd

from anomaly_agent.report import anomalies_to_rows


def build_excel_report(df, anomalies, period):
    """Return the bytes of an Excel file with three sheets: Summary, Anomalies, Data."""
    high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")
    summary = pd.DataFrame(
        {
            "Item": ["Period", "Rows analysed", "Anomalies found", "HIGH severity"],
            "Value": [period, len(df), len(anomalies), high_count],
        }
    )
    columns = ["Metric", "Severity", "Change", "Previous", "Latest", "Z-score"]
    table = pd.DataFrame(anomalies_to_rows(anomalies), columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        table.to_excel(writer, sheet_name="Anomalies", index=False)
        df.to_excel(writer, sheet_name="Data", index=False)

        # make every column wide enough to read
        for sheet in writer.book.worksheets:
            for column in sheet.columns:
                longest = max(len(str(cell.value)) for cell in column if cell.value is not None)
                sheet.column_dimensions[column[0].column_letter].width = min(longest + 2, 50)

    return output.getvalue()
