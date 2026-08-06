from io import BytesIO

import pytest
from openpyxl import Workbook

from procurawise.reports.exceptions import RequirementsImportError
from procurawise.reports.import_parsing import parse_requirements_file


def _csv_bytes(header: str, *rows: str) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


def test_parse_csv_detects_columns_and_rows() -> None:
    content = _csv_bytes(
        "Dimension,Categoria,Titulo,Descripcion,Prioridad,Peso,Obligatorio",
        "functional,Core,Req 1,d,important,40,true",
    )
    columns, rows, mapping = parse_requirements_file("requerimientos.csv", content)
    assert columns == [
        "Dimension",
        "Categoria",
        "Titulo",
        "Descripcion",
        "Prioridad",
        "Peso",
        "Obligatorio",
    ]
    assert rows == [
        {
            "Dimension": "functional",
            "Categoria": "Core",
            "Titulo": "Req 1",
            "Descripcion": "d",
            "Prioridad": "important",
            "Peso": "40",
            "Obligatorio": "true",
        }
    ]
    assert mapping == {
        "dimension": "Dimension",
        "category": "Categoria",
        "title": "Titulo",
        "description": "Descripcion",
        "priority": "Prioridad",
        "weight": "Peso",
        "required": "Obligatorio",
    }


def test_parse_csv_handles_utf8_bom() -> None:
    content = b"\xef\xbb\xbfTitle,Peso\nReq 1,40\n"
    columns, rows, _mapping = parse_requirements_file("r.csv", content)
    assert columns == ["Title", "Peso"]
    assert rows == [{"Title": "Req 1", "Peso": "40"}]


def test_parse_xlsx_detects_columns_and_rows() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Title", "Category", "Weight"])
    sheet.append(["Req 1", "Core", 40])
    buffer = BytesIO()
    workbook.save(buffer)

    columns, rows, mapping = parse_requirements_file("r.xlsx", buffer.getvalue())
    assert columns == ["Title", "Category", "Weight"]
    assert rows == [{"Title": "Req 1", "Category": "Core", "Weight": 40}]
    assert mapping["title"] == "Title"
    assert mapping["weight"] == "Weight"


def test_parse_xlsx_skips_fully_empty_rows() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Title"])
    sheet.append(["Req 1"])
    sheet.append([None])
    sheet.append(["Req 2"])
    buffer = BytesIO()
    workbook.save(buffer)

    _columns, rows, _mapping = parse_requirements_file("r.xlsx", buffer.getvalue())
    assert rows == [{"Title": "Req 1"}, {"Title": "Req 2"}]


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(RequirementsImportError):
        parse_requirements_file("r.pdf", b"not-a-spreadsheet")


def test_empty_file_is_rejected() -> None:
    with pytest.raises(RequirementsImportError):
        parse_requirements_file("r.csv", b"")


def test_csv_with_no_columns_is_rejected() -> None:
    with pytest.raises(RequirementsImportError):
        parse_requirements_file("r.csv", b"\n")
