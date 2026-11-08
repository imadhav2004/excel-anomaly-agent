"""The professional PDF report, drawn with fpdf2 only (no extra packages).

Layout: title band, four number boxes, summary, anomalies of the latest period, one small trend chart per
metric (flagged periods in red), forecast table, strongest flags in the file, notes and disclaimer.
"""
from fpdf import FPDF
from fpdf.fonts import FontFace

from anomaly_agent.pdf_report import clean
from anomaly_agent.report_data import fmt

NAVY = (30, 41, 59)
BLUE = (37, 99, 235)
GREY = (100, 116, 139)
LIGHT = (241, 245, 249)
RED = (220, 38, 38)
SEVERITY_FILL = {"HIGH": (254, 202, 202), "MEDIUM": (254, 240, 199), "LOW": (219, 234, 254)}
GRADE_FILL = {"good": (209, 250, 229), "fair": (254, 240, 199), "poor": (254, 202, 202)}
MAX_CHARTS = 12
MAX_SCAN_ROWS = 15
BOTTOM = 275  # a new page starts when something would pass this height (mm)


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)
        self.alias_nb_pages()

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, f"Excel Anomaly Agent  |  page {self.page_no()} of {{nb}}", align="C")


def heading(pdf, text):
    if pdf.get_y() > BOTTOM - 30:
        pdf.add_page()
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, clean(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BLUE)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 25, pdf.get_y())
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)


def paragraph(pdf, text, size=10, style="", colour=(0, 0, 0), bullet=False):
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(*colour)
    prefix = "- " if bullet else ""
    pdf.multi_cell(0, 5.2, clean(prefix + text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def table_style(pdf):
    """The chart code leaves red and blue colours behind. Reset them so tables are plain."""
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.2)
    pdf.set_text_color(0, 0, 0)
    return {"borders_layout": "HORIZONTAL_LINES", "cell_fill_color": (248, 250, 252), "cell_fill_mode": "ROWS"}


def title_band(pdf, data):
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 38, style="F")
    pdf.set_xy(15, 10)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, "Excel Anomaly Agent", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Anomaly and forecast report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, clean(f"File: {data['file']}   |   Latest period: {data['period']}   |   Created: {data['created']:%d %b %Y %H:%M}"))
    pdf.set_y(46)
    pdf.set_text_color(0, 0, 0)


def kpi_boxes(pdf, kpis):
    width = (pdf.w - pdf.l_margin - pdf.r_margin - 3 * 4) / 4
    top = pdf.get_y()
    for i, (label, value) in enumerate(kpis):
        left = pdf.l_margin + i * (width + 4)
        pdf.set_fill_color(*LIGHT)
        pdf.rect(left, top, width, 20, style="F")
        pdf.set_xy(left, top + 3)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*NAVY)
        pdf.cell(width, 8, clean(value), align="C")
        pdf.set_xy(left, top + 12)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY)
        pdf.cell(width, 5, clean(label), align="C")
    pdf.set_y(top + 24)
    pdf.set_text_color(0, 0, 0)


def draw_chart(pdf, left, top, width, height, metric, info):
    """A small line chart. Flagged periods are red dots. Needs no image library."""
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.set_xy(left, top)
    pdf.cell(width, 5, clean(metric)[:40])
    plot_top, plot_height = top + 7, height - 15
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.2)
    pdf.rect(left, plot_top, width, plot_height)
    points = [(i, v) for i, v in enumerate(info["values"]) if v is not None]
    if len(points) >= 2:
        low, high = min(v for _, v in points), max(v for _, v in points)
        span = (high - low) or 1.0
        last_index = max(len(info["values"]) - 1, 1)

        def place(i, v):
            return left + 1 + (width - 2) * i / last_index, plot_top + plot_height - 1 - (plot_height - 2) * (v - low) / span

        pdf.set_draw_color(*BLUE)
        pdf.set_line_width(0.4)
        previous = None
        for i, v in points:
            x, y = place(i, v)
            if previous is not None:
                pdf.line(previous[0], previous[1], x, y)
            previous = (x, y)
        pdf.set_fill_color(*RED)
        for i in info["flagged"]:
            if info["values"][i] is not None:
                x, y = place(i, info["values"][i])
                pdf.circle(x - 0.8, y - 0.8, 1.6, style="F")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*GREY)
        pdf.set_xy(left, plot_top + plot_height + 0.5)
        pdf.cell(width / 2, 4, clean(f"{info['dates'][0]:%b %Y}  (min {fmt(low)})"))
        pdf.cell(width / 2, 4, clean(f"max {fmt(high)}  {info['dates'][-1]:%b %Y}"), align="R")
    pdf.set_text_color(0, 0, 0)


def charts(pdf, series):
    width, height, gap = 88, 50, 4
    names = list(series)[:MAX_CHARTS]
    for start in range(0, len(names), 2):
        if pdf.get_y() + height > BOTTOM:
            pdf.add_page()
        top = pdf.get_y()
        for offset, metric in enumerate(names[start : start + 2]):
            draw_chart(pdf, pdf.l_margin + offset * (width + gap), top, width, height, metric, series[metric])
        pdf.set_y(top + height + 2)
    if len(series) > MAX_CHARTS:
        paragraph(pdf, f"Only the first {MAX_CHARTS} of {len(series)} metrics are charted here. The Excel report has all of them.", 8, "I", GREY)
    paragraph(pdf, "Red dots are periods flagged by the scan.", 8, "I", GREY)


def build_full_pdf(data, compress=True):
    """Return the bytes of the report. (Tests pass compress=False so the text can be searched.)"""
    pdf = ReportPDF()
    pdf.set_compression(compress)
    pdf.add_page()
    title_band(pdf, data)
    kpi_boxes(pdf, data["kpis"])

    heading(pdf, "Summary")
    for line in data["summary_lines"]:
        paragraph(pdf, line, bullet=True)
    if data["ai_summary"]:
        pdf.ln(2)
        paragraph(pdf, "AI summary (written by Gemini from the computed numbers, may be wrong):", 9, "B", GREY)
        paragraph(pdf, data["ai_summary"], 9)

    heading(pdf, f"Anomalies in the latest period ({data['period']})")
    if not data["latest"]:
        paragraph(pdf, "No anomalies were flagged in the latest period.")
    else:
        head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
        pdf.set_font("Helvetica", "", 9)
        with pdf.table(**table_style(pdf), col_widths=(32, 22, 40, 28, 28, 30), headings_style=head, text_align="LEFT") as table:
            row = table.row()
            for name in ("Metric", "Severity", "Change", "Previous", "Latest", "Agreement"):
                row.cell(name)
            for item in data["latest"]:
                row = table.row()
                row.cell(clean(str(item["metric"])))
                row.cell(item["severity"], style=FontFace(emphasis="BOLD", fill_color=SEVERITY_FILL[item["severity"]]))
                row.cell(clean(item["change"]))
                row.cell(fmt(item["previous"]))
                row.cell(fmt(item["latest"]))
                row.cell(item["agreement"])
        pdf.ln(3)
        for item in data["latest"]:
            if item["note"]:
                label = "AI suggestion" if item["note_source"] == "AI" else "built-in note"
                paragraph(pdf, f"{item['metric']} ({label})", 9, "B")
                paragraph(pdf, item["note"], 9, colour=(51, 65, 85))
                pdf.ln(1)

    heading(pdf, "Trend of every metric")
    charts(pdf, data["series"])

    heading(pdf, f"Forecast (next {data['horizon']} periods)")
    ok = [f for f in data["forecasts"] if "rows" in f]
    if not ok:
        paragraph(pdf, "No forecast could be made for this file.")
    else:
        head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
        pdf.set_font("Helvetica", "", 9)
        with pdf.table(**table_style(pdf), col_widths=(30, 22, 30, 30, 30, 38), headings_style=head, text_align="LEFT") as table:
            row = table.row()
            for name in ("Metric", "Period", "Forecast", "Lower 95%", "Upper 95%", "Accuracy check"):
                row.cell(name)
            for f in ok:
                for i, r in enumerate(f["rows"]):
                    row = table.row()
                    row.cell(clean(f["metric"]) if i == 0 else "")
                    row.cell(r["period_label"])
                    row.cell(fmt(r["forecast"]))
                    row.cell(fmt(r["lower"]))
                    row.cell(fmt(r["upper"]))
                    if i == 0:
                        mape = "n/a" if f["mape"] is None else f"{f['mape']:.1%} error"
                        row.cell(f"{f['grade']} ({mape})", style=FontFace(emphasis="BOLD", fill_color=GRADE_FILL[f["grade"]]))
                    else:
                        row.cell("")
        pdf.ln(2)
        for f in ok:
            paragraph(pdf, f"{f['metric']}: {f['verdict']}", 8, colour=GREY)
    for f in data["forecasts"]:
        if "error" in f:
            paragraph(pdf, f"{f['metric']}: no forecast. {f['error']}", 8, "I", GREY)

    heading(pdf, "Strongest flags in the whole file")
    top = data["scan"][:MAX_SCAN_ROWS]
    if not top:
        paragraph(pdf, "No period was flagged.")
    else:
        head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
        pdf.set_font("Helvetica", "", 8.5)
        with pdf.table(**table_style(pdf), col_widths=(22, 30, 20, 20, 26, 26, 36), headings_style=head, text_align="LEFT") as table:
            row = table.row()
            for name in ("Period", "Metric", "Severity", "Direction", "Actual", "Expected", "Agreement"):
                row.cell(name)
            for r in top:
                row = table.row()
                row.cell(r["period_label"])
                row.cell(clean(str(r["metric"])))
                row.cell(r["severity"], style=FontFace(emphasis="BOLD", fill_color=SEVERITY_FILL[r["severity"]]))
                row.cell(r["direction"])
                row.cell(fmt(r["actual"]))
                row.cell(fmt(r["expected"]))
                row.cell(r["agreement"])
        if len(data["scan"]) > MAX_SCAN_ROWS:
            paragraph(pdf, f"Showing {MAX_SCAN_ROWS} of {len(data['scan'])}. The Excel and CSV reports list all of them.", 8, "I", GREY)

    heading(pdf, "Data notes and method")
    if data["clean_log"]:
        for line in data["clean_log"]:
            paragraph(pdf, line, 9, bullet=True)
    else:
        paragraph(pdf, "No cleaning was needed.", 9)
    pdf.ln(1)
    for line in data["method_notes"]:
        paragraph(pdf, line, 9, bullet=True)
    pdf.ln(3)
    paragraph(pdf, data["disclaimer"], 8, "I", GREY)
    return bytes(pdf.output())
