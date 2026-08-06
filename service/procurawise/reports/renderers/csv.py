"""Fase 23 (ADR 0023) - stdlib csv, no new dependency. CSV has no concept of
multiple sheets, so every ReportSheet is flattened into one file with a
leading "Hoja" column identifying which sheet each row came from."""

import csv as csv_module
from io import StringIO

from procurawise.reports.render_types import ReportWorkbook
from procurawise.reports.renderers.xlsx import escape_cell


def render(workbook_data: ReportWorkbook) -> bytes:
    buffer = StringIO()
    writer = csv_module.writer(buffer)
    multi_sheet = len(workbook_data.sheets) > 1
    for sheet in workbook_data.sheets:
        if multi_sheet:
            writer.writerow(["Hoja", *sheet.headers])
        else:
            writer.writerow(sheet.headers)
        for row in sheet.rows:
            escaped = [escape_cell(value) for value in row]
            writer.writerow([sheet.name, *escaped] if multi_sheet else escaped)
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 CSV correctly
