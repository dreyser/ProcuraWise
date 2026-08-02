from typing import Final

from procurawise.agreements.models import AgreementType

# Fase 15 (ADR 0014, founder decision D4 of the planning session): a single
# platform-wide legal text per type, versioned as plain constants here - not
# a per-tenant-editable collection, and not administrable via any UI this
# phase (same minimal-admin precedent as curated_sources: mutable-content
# admin screens are explicitly out of scope). Bumping a version string here
# means every vendor contact - even one with evaluations already in
# progress - must re-accept before their next action in the vendor portal.
# There is deliberately no grandfathering (founder decision D4): an old
# acceptance never remains valid once the current version differs from it.
CURRENT_NDA_VERSION: Final[str] = "2026-08-v1"
CURRENT_CONFLICT_OF_INTEREST_VERSION: Final[str] = "2026-08-v1"

_NDA_TEXT: Final[str] = (
    "Acuerdo de Confidencialidad (NDA)\n\n"
    "Al aceptar este acuerdo, usted, en representacion de la organizacion "
    "proveedora, se compromete a mantener bajo estricta confidencialidad "
    "toda la informacion compartida por el comprador a traves de "
    "ProcuraWise durante el proceso de RFP - incluyendo, sin limitarse a, "
    "requerimientos, criterios de evaluacion, comunicaciones y cualquier "
    "documento o dato al que tenga acceso a traves de esta plataforma. "
    "Esta obligacion de confidencialidad sobrevive a la conclusion del "
    "proceso de evaluacion."
)

_CONFLICT_OF_INTEREST_TEXT: Final[str] = (
    "Declaracion de Conflicto de Interes\n\n"
    "Al aceptar esta declaracion, usted confirma que ni usted ni la "
    "organizacion proveedora que representa tienen un conflicto de interes "
    "actual o potencial con el comprador o con el proceso de evaluacion en "
    "curso que no haya sido divulgado explicitamente. Usted se compromete a "
    "notificar de inmediato cualquier conflicto de interes que surja "
    "durante el proceso."
)

_CURRENT_VERSION_BY_TYPE: Final[dict[AgreementType, str]] = {
    "nda": CURRENT_NDA_VERSION,
    "conflict_of_interest": CURRENT_CONFLICT_OF_INTEREST_VERSION,
}

_TEXT_BY_TYPE: Final[dict[AgreementType, str]] = {
    "nda": _NDA_TEXT,
    "conflict_of_interest": _CONFLICT_OF_INTEREST_TEXT,
}


def current_version(agreement_type: AgreementType) -> str:
    return _CURRENT_VERSION_BY_TYPE[agreement_type]


def text_for(agreement_type: AgreementType) -> str:
    return _TEXT_BY_TYPE[agreement_type]
