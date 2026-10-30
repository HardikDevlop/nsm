from __future__ import annotations

from datetime import datetime
from io import BytesIO


def generate_report_pdf(
    rows: list[dict[str, object]],
    *,
    title: str = "Network Monitoring Report",
    period_start: datetime | str | None = None,
    period_end: datetime | str | None = None,
) -> bytes:
    """Render existing management-report rows as a paginated PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
        pageCompression=0,
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("ReportHeading", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=19, textColor=colors.HexColor("#17365D"), spaceAfter=5 * mm)
    metadata = ParagraphStyle("ReportMetadata", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8, leading=10, textColor=colors.HexColor("#4B5563"), spaceAfter=5 * mm)
    cell = ParagraphStyle("ReportCell", parent=styles["Normal"], fontSize=6.5, leading=8, wordWrap="CJK")
    header = ParagraphStyle("ReportHeader", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)

    def text(value: object) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        return str(value)

    def safe(value: object, style: ParagraphStyle = cell) -> Paragraph:
        return Paragraph(text(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)

    headers = list(rows[0].keys()) if rows else ["device_id", "hostname"]
    table_data = [[safe(name, header) for name in headers]]
    table_data.extend([[safe(row.get(name)) for name in headers] for row in rows])
    available_width = landscape(A4)[0] - document.leftMargin - document.rightMargin
    column_width = available_width / max(1, len(headers))
    table = LongTable(table_data, colWidths=[column_width] * len(headers), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    period = f"Period: {text(period_start)} to {text(period_end)}" if period_start is not None or period_end is not None else "Period: —"
    document.build([Paragraph(title, heading), Paragraph(period, metadata), table])
    return output.getvalue()
