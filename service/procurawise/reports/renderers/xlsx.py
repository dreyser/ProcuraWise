"""Fase 23 (ADR 0023) - the only module (besides csv.py, which shares the
escaping helper) allowed to import openpyxl for writing."""

from io import BytesIO
from typing import Any

from openpyxl import Workbook

from procurawise.reports.render_types import ReportWorkbook

# OWASP CSV/formula injection: a cell value that a spreadsheet application
# would interpret as a formula (leading =, +, -, @) is prefixed with a
# leading apostrophe, which every mainstream spreadsheet app renders as a
# literal, inert text prefix rather than executing it as a formula. Applied
# uniformly regardless of column - no per-column exception (ADR 0023).
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def render(workbook_data: ReportWorkbook) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in workbook_data.sheets:
        worksheet = workbook.create_sheet(title=sheet.name[:31])  # Excel sheet-name length limit
        worksheet.append(sheet.headers)
        for row in sheet.rows:
            worksheet.append([escape_cell(value) for value in row])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
