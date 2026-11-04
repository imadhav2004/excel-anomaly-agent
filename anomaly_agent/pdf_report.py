from datetime import datetime

from fpdf import FPDF

from anomaly_agent.report import anomalies_to_rows

# The built-in PDF fonts only know basic Latin characters, so we swap fancy ones first
REPLACEMENTS = {
    "–": "-",
    "—": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "→": "->",
}


def clean(text):
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def build_pdf_report(anomalies, explanations, period, rows_analysed):
    """Return the bytes of a one or two page PDF report."""
    high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "Excel Anomaly Agent - Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(
        0, 7, f"Period: {period}    Created: {datetime.now():%d %b %Y}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(3)
    pdf.multi_cell(
        0, 6,
        f"Rows analysed: {rows_analysed}. Anomalies found: {len(anomalies)} "
        f"({high_count} HIGH severity).",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    if not anomalies:
        pdf.multi_cell(0, 6, "No anomalies found.", new_x="LMARGIN", new_y="NEXT")
    else:
        headers = ["Metric", "Severity", "Change", "Previous", "Latest"]
        with pdf.table(col_widths=(34, 24, 44, 28, 28), text_align="LEFT") as table:
            header_row = table.row()
            for name in headers:
                header_row.cell(name)
            for row in anomalies_to_rows(anomalies):
                cells = table.row()
                cells.cell(clean(str(row["Metric"])))
                cells.cell(row["Severity"])
                cells.cell(clean(row["Change"]))
                cells.cell(f"{row['Previous']:,.0f}")
                cells.cell(f"{row['Latest']:,.0f}")

        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Why it matters", new_x="LMARGIN", new_y="NEXT")

        for a in anomalies:
            item = explanations.get(a["metric"])
            if not item:
                continue
            label = "AI suggestion" if item["source"] == "AI" else "built-in note"
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, clean(f"{a['metric']} ({label})"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, clean(item["text"]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0, 5,
        "These are statistical alerts, not confirmed business problems. "
        "AI suggestions are possibilities, not facts. Please check the data before acting.",
        new_x="LMARGIN", new_y="NEXT",
    )
    return bytes(pdf.output())
