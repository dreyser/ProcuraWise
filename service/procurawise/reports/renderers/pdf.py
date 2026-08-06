"""Fase 23 (ADR 0023) - the only module besides docx.py/xlsx.py/csv.py
allowed to import reportlab (CLAUDE.md S5.1's import-boundary principle,
applied here to report-generation libraries instead of AI providers)."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from procurawise.reports.render_types import ReportDocument

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("ReportTitle", parent=_STYLES["Title"])
_SUBTITLE_STYLE = ParagraphStyle("ReportSubtitle", parent=_STYLES["Heading2"])
_META_STYLE = ParagraphStyle("ReportMeta", parent=_STYLES["Normal"], textColor=colors.grey)
_HEADING_STYLE = _STYLES["Heading3"]
_BODY_STYLE = _STYLES["Normal"]


def _table_flowable(headers: list[str], rows: list[list[str]]) -> Table:
    data = [headers, *rows] if rows else [headers]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ]
        )
    )
    return table


def _page_decoration(canvas, doc) -> None:  # noqa: ANN001 - reportlab callback signature
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(doc.pagesize[0] - 0.5 * inch, 0.4 * inch, f"Página {doc.page}")
    canvas.drawString(0.5 * inch, 0.4 * inch, "ProcuraWise")
    canvas.restoreState()


def render(document: ReportDocument) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        title=document.title,
    )
    story = [
        Paragraph(document.title, _TITLE_STYLE),
        Paragraph(document.subtitle, _SUBTITLE_STYLE),
        Spacer(1, 6),
    ]
    for line in document.metadata_lines:
        story.append(Paragraph(line, _META_STYLE))
    story.append(Spacer(1, 12))
    for section in document.sections:
        story.append(Paragraph(section.heading, _HEADING_STYLE))
        for paragraph in section.paragraphs:
            story.append(Paragraph(paragraph, _BODY_STYLE))
        if section.table is not None:
            story.append(Spacer(1, 4))
            story.append(_table_flowable(section.table.headers, section.table.rows))
        story.append(Spacer(1, 12))
    doc.build(story, onFirstPage=_page_decoration, onLaterPages=_page_decoration)
    return buffer.getvalue()
