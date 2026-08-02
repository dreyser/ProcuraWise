from procurawise.agreements import legal_content
from procurawise.agreements.models import Agreement, AgreementType
from procurawise.agreements.repository import AgreementRepository

ALL_AGREEMENT_TYPES: tuple[AgreementType, ...] = ("nda", "conflict_of_interest")


class AgreementService:
    """Backs the vendor-portal Agreement gate (Fase 15 backlog criterion:
    "Proveedor no accede al formulario de respuesta sin aceptar ambos
    Agreement"). Every acceptance is per-user_id (ADR 0014) - a new
    collaborator on the same vendor_org_id never inherits another
    collaborator's acceptance."""

    def __init__(self, repository: AgreementRepository) -> None:
        self._repository = repository

    def has_current_acceptance(
        self, tenant_id: str, user_id: str, agreement_type: AgreementType
    ) -> bool:
        latest = self._repository.find_latest(tenant_id, user_id, agreement_type)
        if latest is None:
            return False
        return bool(latest["version"] == legal_content.current_version(agreement_type))

    def missing_agreement_types(self, tenant_id: str, user_id: str) -> list[AgreementType]:
        return [
            agreement_type
            for agreement_type in ALL_AGREEMENT_TYPES
            if not self.has_current_acceptance(tenant_id, user_id, agreement_type)
        ]

    def accept(
        self,
        tenant_id: str,
        user_id: str,
        membership_id: str,
        agreement_type: AgreementType,
        *,
        ip: str,
        user_agent: str | None,
    ) -> Agreement:
        agreement = Agreement.create(
            tenant_id=tenant_id,
            user_id=user_id,
            membership_id=membership_id,
            type=agreement_type,
            version=legal_content.current_version(agreement_type),
            ip=ip,
            user_agent=user_agent,
        )
        self._repository.insert(tenant_id, agreement.to_document())
        return agreement
