from dataclasses import dataclass, field
from typing import Any

# Fase 23 - generic intermediate representation produced by reports/assembly.py
# and consumed by reports/renderers/{pdf,docx}.py (ReportDocument) or
# reports/renderers/{xlsx,csv}.py (ReportSheet). Keeps the 8 assembly
# functions decoupled from the 4 rendering engines - a renderer never reaches
# into evaluations/scoring/decisions, and assembly never imports reportlab/
# openpyxl/docx (ADR 0023's import-boundary principle).


@dataclass(frozen=True)
class ReportTable:
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class ReportSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    table: ReportTable | None = None


@dataclass(frozen=True)
class ReportDocument:
    """Feeds the pdf/docx renderers - one of the two shapes assembly.py can
    produce, used by the 6 narrative report types."""

    title: str
    subtitle: str
    metadata_lines: list[str]
    sections: list[ReportSection]


@dataclass(frozen=True)
class ReportSheet:
    name: str
    headers: list[str]
    rows: list[list[Any]]


@dataclass(frozen=True)
class ReportWorkbook:
    """Feeds the xlsx/csv renderers - the other shape assembly.py can
    produce, used by the 2 tabular report types. csv.py flattens every sheet
    into one file (CSV has no concept of multiple sheets); xlsx.py writes
    one worksheet per ReportSheet."""

    title: str
    metadata_lines: list[str]
    sheets: list[ReportSheet]
