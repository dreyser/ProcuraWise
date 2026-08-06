from typing import Any

from procurawise.evaluations.schemas import RequirementCreateRequest, RequirementResponse
from procurawise.shared.api_models import APIModel


class RequirementImportPreviewResponse(APIModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    suggested_mapping: dict[str, str]


class RequirementImportConfirmRequest(APIModel):
    """Reuses RequirementCreateRequest verbatim - the client resolves the
    column mapping locally (against the preview's `columns`/
    `suggested_mapping`) and sends back already-mapped, schema-valid
    Requirement rows, same shape manual entry already uses."""

    requirements: list[RequirementCreateRequest]


class RequirementImportConfirmResponse(APIModel):
    requirements: list[RequirementResponse]
