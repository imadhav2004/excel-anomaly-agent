"""The professional Excel report: formatted sheets and real Excel charts (they stay editable in Excel).

Sheets: Summary, Latest anomalies, All flags, Forecast, Data, Charts, Notes.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NAVY = "1E293B"
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
HEAD_FONT = Font(bold=True, color="FFFFFF")
SEVERITY_FILL = {
    "HIGH": PatternFill("solid", fgColor="FECACA"),
    "MEDIUM": PatternFill("solid", fgColor="FEF0C7"),
    "LOW": PatternFill("solid", fgColor="DBEAFE"),
}
GRADE_FILL = {
    "good": PatternFill("solid", fgColor="D1FAE5"),
    "fair": PatternFill("solid", fgColor="FEF0C7"),
    "poor": PatternFill("solid", fgColor="FECACA"),
}
MAX_CHARTS = 12


def write_table(sheet, top, headers, rows, number_format="#,##0.00"):
    """Write a header row and the rows under it. Returns the row number after the table."""
    for col, name in enumerate(headers, start=1):
        cell = sheet.cell(row=top, column=col, value=name)
        if isinstance(name, str) and name.startswith("="):
            cell.data_type = "s"
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(vertical="center")
    for r, row in enumerate(rows, start=top + 1):
        for col, value in enumerate(row, start=1):
            cell = sheet.cell(row=r, column=col, value=value)
            if isinstance(value, str) and value.startswith("="):
                cell.data_type = "s"  # text from the uploaded file is never a formula
            if isinstance(value, float):
                cell.number_format = number_format
    return top + 1 + len(rows)


def fit_columns(sheet, minimum=10, maximum=60):
    for column in sheet.columns:
        longest = max((len(str(c.value)) for c in column if c.value is not None), default=0)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = max(minimum, min(longest + 2, maximum))


def colour_column(sheet, column, first_row, last_row, fills):
    for r in range(first_row, last_row + 1):
        cell = sheet.cell(row=r, column=column)
        if cell.value in fills:
            cell.fill = fills[cell.value]
            cell.font = Font(bold=True)


def build_full_excel(data, df, date_column):
    """Return the bytes of the .xlsx file. `df` is the cleaned table shown in the Data sheet."""
    book = Workbook()

    # ---- Summary ----
    sheet = book.active
    sheet.title = "Summary"
    sheet["A1"] = "Excel Anomaly Agent report"
    sheet["A1"].font = Font(bold=True, size=16, color=NAVY)
    sheet["A2"] = f"File: {data['file']}   |   Latest period: {data['period']}   |   Data: {data['date_range']}"
    sheet["A3"] = f"Created: {data['created']:%d %b %Y %H:%M}"
    row = write_table(sheet, 5, ["Measure", "Value"], [list(k) for k in data["kpis"]])
    sheet.cell(row=row + 1, column=1, value="Summary").font = Font(bold=True, size=12)
    row += 2
    for line in data["summary_lines"]:
        sheet.cell(row=row, column=1, value=f"- {line}")
        row += 1
    if data["ai_summary"]:
        row += 1
        sheet.cell(row=row, column=1, value="AI summary (Gemini, from the computed numbers; may be wrong)").font = Font(bold=True)
        for line in data["ai_summary"].splitlines():
            row += 1
            sheet.cell(row=row, column=1, value=line)
    fit_columns(sheet, maximum=40)

    # ---- Latest anomalies ----
    sheet = book.create_sheet("Latest anomalies")
    rows = [
        [i["metric"], i["severity"], i["direction"], i["change"], i["previous"], i["latest"], i["agreement"], i["note"],
         "AI" if i["note_source"] == "AI" else "built-in"]
        for i in data["latest"]
    ]
    end = write_table(sheet, 1, ["Metric", "Severity", "Direction", "Change", "Previous", "Latest", "Agreement", "Why it matters", "Note by"], rows)
    colour_column(sheet, 2, 2, end - 1, SEVERITY_FILL)
    if not rows:
        sheet["A3"] = f"No anomalies were flagged in {data['period']}."
    sheet.freeze_panes = "A2"
    fit_columns(sheet, maximum=70)

    # ---- All flags ----
    sheet = book.create_sheet("All flags")
    rows = [
        [r["period"].to_pydatetime().date(), r["metric"], r["severity"], r["direction"], r["actual"], r["expected"],
         r["deviation_pct"], r["agreement"], r["methods"], r["explanation"]]
        for r in data["scan"]
    ]
    end = write_table(sheet, 1, ["Period", "Metric", "Severity", "Direction", "Actual", "Expected", "Deviation", "Agreement", "Methods", "Explanation"], rows)
    for r in range(2, end):
        sheet.cell(row=r, column=1).number_format = "mmm yyyy"
        sheet.cell(row=r, column=7).number_format = "0.0%"
    colour_column(sheet, 3, 2, end - 1, SEVERITY_FILL)
    sheet.freeze_panes = "A2"
    if rows:
        sheet.auto_filter.ref = f"A1:J{end - 1}"
    fit_columns(sheet, maximum=70)

    # ---- Forecast ----
    sheet = book.create_sheet("Forecast")
    rows, grades = [], {}
    for f in data["forecasts"]:
        if "rows" not in f:
            rows.append([f["metric"], "no forecast", None, None, None, f["error"], None])
            continue
        for i, r in enumerate(f["rows"]):
            rows.append([f["metric"], r["period"].to_pydatetime().date(), r["forecast"], r["lower"], r["upper"],
                         f["verdict"] if i == 0 else None, f["grade"] if i == 0 else None])
    end = write_table(sheet, 1, ["Metric", "Period", "Forecast", "Lower 95%", "Upper 95%", "Accuracy check", "Grade"], rows)
    for r in range(2, end):
        if hasattr(sheet.cell(row=r, column=2).value, "year"):
            sheet.cell(row=r, column=2).number_format = "mmm yyyy"
    colour_column(sheet, 7, 2, end - 1, GRADE_FILL)
    sheet.freeze_panes = "A2"
    fit_columns(sheet, maximum=70)

    # ---- Data + Charts ----
    data_sheet = book.create_sheet("Data")
    columns = list(df.columns)
    rows = [[v.to_pydatetime().date() if hasattr(v, "to_pydatetime") else (None if v != v else v) for v in rec]
            for rec in df.itertuples(index=False)]
    end = write_table(data_sheet, 1, columns, rows)
    for r in range(2, end):
        data_sheet.cell(row=r, column=columns.index(date_column) + 1).number_format = "mmm yyyy"
    data_sheet.freeze_panes = "B2"
    fit_columns(data_sheet, maximum=30)

    chart_sheet = book.create_sheet("Charts")
    chart_sheet["A1"] = "One chart per metric (editable Excel charts). The numbers are in the Data sheet."
    date_col = columns.index(date_column) + 1
    metrics = [c for c in columns if c != date_column][:MAX_CHARTS]
    for n, metric in enumerate(metrics):
        col = columns.index(metric) + 1
        chart = LineChart()
        chart.title = str(metric)
        chart.height, chart.width = 7.5, 15
        chart.legend = None
        chart.add_data(Reference(data_sheet, min_col=col, min_row=1, max_row=end - 1), titles_from_data=True)
        chart.set_categories(Reference(data_sheet, min_col=date_col, min_row=2, max_row=end - 1))
        for line in chart.series:
            line.smooth = False  # straight lines show the real values, not a smoothed curve
        chart.x_axis.number_format = "mmm yy"
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart_sheet.add_chart(chart, f"{'A' if n % 2 == 0 else 'K'}{3 + (n // 2) * 16}")

    # ---- Notes ----
    sheet = book.create_sheet("Notes")
    sheet["A1"] = "Data notes"
    sheet["A1"].font = Font(bold=True, size=12)
    row = 2
    for line in data["clean_log"] or ["No cleaning was needed."]:
        sheet.cell(row=row, column=1, value=f"- {line}")
        row += 1
    row += 1
    sheet.cell(row=row, column=1, value="Method").font = Font(bold=True, size=12)
    for line in data["method_notes"]:
        row += 1
        sheet.cell(row=row, column=1, value=f"- {line}")
    row += 2
    sheet.cell(row=row, column=1, value=data["disclaimer"]).font = Font(italic=True)
    sheet.column_dimensions["A"].width = 120

    output = BytesIO()
    book.save(output)
    return output.getvalue()
