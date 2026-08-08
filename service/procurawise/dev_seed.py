import logging
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pymongo.database import Database

from procurawise.admin.models import PlatformAdminAccount
from procurawise.admin.repository import PlatformAdminAccountRepository
from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.service import EvaluationService
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.models import Membership, Role, Tenant, User, VendorOrganization
from procurawise.identity.passwords import hash_password
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.logging import configure_logging
from procurawise.shared.mongo import get_database

logger = logging.getLogger("procurawise.dev_seed")

# Known local-dev password for every seeded buyer user (AUTH-PROD) - lets a
# developer exercise the real POST /auth/login form without registering real
# OIDC apps. Never used outside local/test (this whole module is gated to
# that), never a production credential.
DEV_BUYER_PASSWORD = "dev-password-2026"

# Same idea, for the one seeded platform_admin account (Fase 9 Block 4) - lets
# POST /api/v1/admin/auth/login be exercised locally without a real
# provisioning step.
DEV_ADMIN_PASSWORD = "dev-admin-password-2026"
DEV_ADMIN_EMAIL = "platform-admin@dev.procurawise.local"

# Fase 15: vendor_contact now authenticates via a real password too (POST
# /api/v1/vendor-auth/login), same idea as DEV_BUYER_PASSWORD above - lets a
# developer exercise the real vendor login form without hand-crafting an
# invitation-acceptance flow every time. The seeded users are still also
# reachable via the interim dev-header mechanism (unchanged - that mechanism
# is not deleted, only no longer accepted by vendor_portal routes).
DEV_VENDOR_PASSWORD = "dev-vendor-password-2026"

# Collections this script owns. `make seed-reset` drops exactly these, nothing
# from a future bounded context - keep this list in sync as seed-dev grows.
SEEDED_COLLECTIONS = [
    "memberships",
    "vendor_organizations",
    "users",
    "tenants",
    "evaluations",
    "proposals",
    "scores",
    "platform_admins",
    "evaluation_snapshots",
    "vendor_invitations",
    "agreements",
]


def _require_dev_environment(settings: Settings) -> None:
    if settings.environment not in ("local", "test"):
        raise RuntimeError(
            "seed-dev/seed-reset solo pueden correr con environment=local o environment=test "
            f"(actual: {settings.environment!r})"
        )


def _get_or_create_tenant(tenants: TenantRepository, slug: str, name: str) -> Tenant:
    existing = tenants.find_by_slug(slug)
    if existing is not None:
        return Tenant.from_document(existing)
    tenant = Tenant.create(slug=slug, name=name)
    tenants.insert(tenant.to_document())
    return tenant


def _get_or_create_user(
    users: UserRepository, email: str, display_name: str, password: str | None = None
) -> User:
    existing = users.find_by_email(email)
    if existing is not None:
        return User.from_document(existing)
    password_hash = hash_password(password) if password else None
    user = User.create(display_name=display_name, email=email, password_hash=password_hash)
    users.insert(user.to_document())
    return user


def _get_or_create_vendor_org(
    vendor_orgs: VendorOrganizationRepository, tenant: Tenant, name: str
) -> VendorOrganization:
    existing = vendor_orgs.find_by_name(tenant.id, name)
    if existing is not None:
        return VendorOrganization.from_document(existing)
    vendor_org = VendorOrganization.create(tenant_id=tenant.id, name=name)
    vendor_orgs.insert(tenant.id, vendor_org.to_document())
    return vendor_org


def _get_or_create_platform_admin(
    admins: PlatformAdminAccountRepository, email: str, display_name: str, password: str
) -> PlatformAdminAccount:
    existing = admins.find_by_email(email)
    if existing is not None:
        return PlatformAdminAccount.from_document(existing)
    account = PlatformAdminAccount.create(
        email=email, display_name=display_name, password_hash=hash_password(password)
    )
    admins.insert(account.to_document())
    return account


def _get_or_create_membership(
    memberships: MembershipRepository,
    tenant: Tenant,
    user: User,
    role: Role,
    vendor_org_id: str | None = None,
) -> Membership:
    existing = memberships.find_one_for(tenant.id, user.id, role, vendor_org_id)
    if existing is not None:
        return Membership.from_document(existing)
    membership = Membership.create(
        tenant_id=tenant.id, user_id=user.id, role=role, vendor_org_id=vendor_org_id
    )
    memberships.insert(membership.to_document())
    return membership


def _get_or_create_evaluation(
    evaluations: EvaluationRepository,
    proposals: ProposalRepository,
    tenant: Tenant,
    owner: Membership,
    vendor_org: VendorOrganization,
    name: str,
) -> Evaluation:
    existing = next((doc for doc in evaluations.find_many(tenant.id) if doc["name"] == name), None)
    if existing is not None:
        return Evaluation.from_document(existing)

    evaluation = Evaluation.create(
        tenant_id=tenant.id,
        name=name,
        description="Evaluacion de ejemplo generada por seed-dev",
        created_by_membership_id=owner.id,
    )
    functional_requirement = Requirement.create(
        dimension="functional",
        category="Capacidades",
        title="Gestion de flujos de aprobacion",
        description="La solucion debe soportar flujos de aprobacion configurables.",
        priority="mandatory",
        response_type="compliant_status",
        weight=40.0,
        required=True,
        display_order=1,
        buyer_guidance="Describir el motor de flujos disponible.",
    )
    technical_requirement = Requirement.create(
        dimension="technical",
        category="Integraciones",
        title="API REST documentada",
        description="La solucion debe exponer una API REST documentada (OpenAPI).",
        priority="important",
        response_type="compliant_status",
        weight=20.0,
        required=True,
        display_order=1,
        buyer_guidance="Adjuntar enlace a la documentacion de la API.",
    )
    evaluation = replace(
        evaluation,
        requirements=[functional_requirement, technical_requirement],
        linked_vendor_count=1,
    )
    evaluations.insert(tenant.id, evaluation.to_document())

    proposal = Proposal.create(
        tenant_id=tenant.id, evaluation_id=evaluation.id, vendor_org_id=vendor_org.id
    )
    proposals.insert(tenant.id, proposal.to_document())

    return evaluation


def _dev_actor(tenant: Tenant, membership: Membership) -> ActorContext:
    return ActorContext(
        membership_id=membership.id,
        user_id=membership.user_id,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        role=membership.role,
        vendor_org_id=membership.vendor_org_id,
        display_name=membership.role,
    )


def _get_or_create_evaluation_with_approval_state(
    settings: Settings,
    db: Database,
    tenant: Tenant,
    owner: Membership,
    approver: Membership,
    vendor_org: VendorOrganization,
    name: str,
    approval_state: str,
) -> Evaluation:
    """Fase 12: seeds one evaluation per approval_status (not_requested is
    already covered by `_get_or_create_evaluation` above) so the new
    approval/publication UI has something to demo/QA against without
    manually driving the whole flow by hand every time (plan §34 Block 6).
    Driven through EvaluationService (not raw document construction) so the
    same validation, transitions, and audit events a real request would
    produce actually run."""
    evaluations = EvaluationRepository(db)
    existing = next((doc for doc in evaluations.find_many(tenant.id) if doc["name"] == name), None)
    if existing is not None:
        return Evaluation.from_document(existing)

    service = EvaluationService(
        evaluations=evaluations,
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        memberships=MembershipRepository(db),
        snapshots=EvaluationSnapshotRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        notifications=build_notification_service(settings),
    )
    owner_actor = _dev_actor(tenant, owner)
    approver_actor = _dev_actor(tenant, approver)

    evaluation = service.create_evaluation(
        tenant.id, owner.id, name, "Evaluacion de ejemplo generada por seed-dev", actor=owner_actor
    )
    service.add_requirement(
        tenant.id,
        evaluation.id,
        dimension="functional",
        category="Capacidades",
        title="Gestion de flujos de aprobacion",
        description="La solucion debe soportar flujos de aprobacion configurables.",
        priority="mandatory",
        response_type="compliant_status",
        weight=40.0,
        required=True,
        display_order=1,
        buyer_guidance="Describir el motor de flujos disponible.",
        options=None,
        actor=owner_actor,
    )
    service.add_requirement(
        tenant.id,
        evaluation.id,
        dimension="technical",
        category="Integraciones",
        title="API REST documentada",
        description="La solucion debe exponer una API REST documentada (OpenAPI).",
        priority="important",
        response_type="compliant_status",
        weight=20.0,
        required=True,
        display_order=1,
        buyer_guidance="Adjuntar enlace a la documentacion de la API.",
        options=None,
        actor=owner_actor,
    )
    service.link_vendor(tenant.id, evaluation.id, vendor_org.id, actor=owner_actor)
    service.update_evaluation(
        tenant.id,
        evaluation.id,
        None,
        None,
        datetime.now(UTC) + timedelta(days=30),
        actor=owner_actor,
    )
    service.set_approver(tenant.id, evaluation.id, approver.id, actor=owner_actor)
    evaluation = service.request_approval(tenant.id, evaluation.id, actor=owner_actor)

    if approval_state == "pending":
        return evaluation
    if approval_state == "rejected":
        return service.reject(
            tenant.id,
            evaluation.id,
            "Falta detalle de integracion con el sistema contable.",
            actor=approver_actor,
        )
    if approval_state == "approved":
        return service.approve(
            tenant.id, evaluation.id, "Cumple los criterios.", actor=approver_actor
        )
    if approval_state == "published":
        service.approve(tenant.id, evaluation.id, "Cumple los criterios.", actor=approver_actor)
        return service.start_collection(tenant.id, evaluation.id, actor=owner_actor)
    raise ValueError(f"unknown approval_state: {approval_state!r}")


def seed(settings: Settings) -> list[Membership]:
    """Idempotent: safe to call repeatedly, never duplicates a tenant, user,
    vendor organization, or membership already seeded."""
    _require_dev_environment(settings)

    db = get_database(settings)
    tenants = TenantRepository(db)
    users = UserRepository(db)
    memberships = MembershipRepository(db)
    vendor_orgs = VendorOrganizationRepository(db)
    admins = PlatformAdminAccountRepository(db)

    _get_or_create_platform_admin(
        admins, DEV_ADMIN_EMAIL, "Platform Admin (dev)", DEV_ADMIN_PASSWORD
    )

    tenant_a = _get_or_create_tenant(tenants, "dev-tenant-a", "Acme Compradora (dev)")
    tenant_b = _get_or_create_tenant(tenants, "dev-tenant-b", "Globex Compradora (dev)")

    # Buyer users get a known local-dev password (DEV_BUYER_PASSWORD) so
    # POST /auth/login is exercisable without real OIDC apps. vendor_user_a/
    # vendor_user_a2 get DEV_VENDOR_PASSWORD (Fase 15) so POST
    # /vendor-auth/login is exercisable the same way.
    owner_a = _get_or_create_user(
        users, "owner.a@dev.procurawise.local", "Owner A", DEV_BUYER_PASSWORD
    )
    evaluator_functional_a = _get_or_create_user(
        users,
        "evaluator.functional.a@dev.procurawise.local",
        "Evaluator Funcional A",
        DEV_BUYER_PASSWORD,
    )
    evaluator_technical_a = _get_or_create_user(
        users,
        "evaluator.technical.a@dev.procurawise.local",
        "Evaluator Tecnico A",
        DEV_BUYER_PASSWORD,
    )
    evaluator_economic_a = _get_or_create_user(
        users,
        "evaluator.economic.a@dev.procurawise.local",
        "Evaluator Economico A",
        DEV_BUYER_PASSWORD,
    )
    collaborator_a = _get_or_create_user(
        users, "collaborator.a@dev.procurawise.local", "Colaborador Interno A", DEV_BUYER_PASSWORD
    )
    approver_a = _get_or_create_user(
        users, "approver.a@dev.procurawise.local", "Aprobador A", DEV_BUYER_PASSWORD
    )
    tenant_admin_a = _get_or_create_user(
        users,
        "tenant-admin.a@dev.procurawise.local",
        "Administrador Cliente A",
        DEV_BUYER_PASSWORD,
    )
    vendor_user_a = _get_or_create_user(
        users, "vendor.a@dev.procurawise.local", "Vendor Contact A", DEV_VENDOR_PASSWORD
    )
    # Fase 15: a second vendor_contact Membership on the *same* vendor_org_a
    # (unlike test_vendor_isolation.py's _create_second_vendor_contact, which
    # deliberately creates a *different* vendor org to test cross-vendor
    # isolation) - this one demonstrates/exercises "multiple collaborators
    # per vendor organization" itself: both see the same proposals, each
    # accepts Agreements individually (ADR 0014's per-user_id grain).
    vendor_user_a2 = _get_or_create_user(
        users,
        "vendor.a2@dev.procurawise.local",
        "Vendor Collaborator A2",
        DEV_VENDOR_PASSWORD,
    )
    owner_b = _get_or_create_user(
        users, "owner.b@dev.procurawise.local", "Owner B", DEV_BUYER_PASSWORD
    )
    evaluator_technical_b = _get_or_create_user(
        users,
        "evaluator.technical.b@dev.procurawise.local",
        "Evaluator Tecnico B",
        DEV_BUYER_PASSWORD,
    )

    vendor_org_a = _get_or_create_vendor_org(vendor_orgs, tenant_a, "Proveedor Uno (dev)")

    owner_a_membership = _get_or_create_membership(
        memberships, tenant_a, owner_a, "evaluation_owner"
    )
    approver_a_membership = _get_or_create_membership(memberships, tenant_a, approver_a, "approver")

    # owner_b also holds a second Membership (approver, same tenant) on
    # purpose: demonstrates that a single User can carry multiple Memberships
    # with distinct roles ("roles acumulables", spec §4.1/FR-005), which the
    # domain model must support without restriction.
    created = [
        owner_a_membership,
        _get_or_create_membership(
            memberships, tenant_a, evaluator_functional_a, "evaluator_functional"
        ),
        _get_or_create_membership(
            memberships, tenant_a, evaluator_technical_a, "evaluator_technical"
        ),
        _get_or_create_membership(
            memberships, tenant_a, evaluator_economic_a, "evaluator_economic"
        ),
        _get_or_create_membership(memberships, tenant_a, collaborator_a, "internal_collaborator"),
        approver_a_membership,
        _get_or_create_membership(memberships, tenant_a, tenant_admin_a, "tenant_admin"),
        _get_or_create_membership(
            memberships, tenant_a, vendor_user_a, "vendor_contact", vendor_org_a.id
        ),
        # A second vendor_contact Membership on the *same* vendor_org_id as
        # the one above (Fase 15: exercises "multiple collaborators per
        # vendor organization"). Listed here, after vendor_user_a, on
        # purpose: tests/conftest.py's `seeded_actors` fixture keys a dict
        # by (tenant_id, role) and keeps the *first* occurrence per key (see
        # that fixture's comment) precisely so this second row never shadows
        # vendor_user_a there - it stays reachable only by email lookup
        # (tests/conftest.py::second_vendor_collaborator_membership_id).
        _get_or_create_membership(
            memberships, tenant_a, vendor_user_a2, "vendor_contact", vendor_org_a.id
        ),
        _get_or_create_membership(memberships, tenant_b, owner_b, "evaluation_owner"),
        _get_or_create_membership(
            memberships, tenant_b, evaluator_technical_b, "evaluator_technical"
        ),
        _get_or_create_membership(memberships, tenant_b, owner_b, "approver"),
    ]

    # Fase 15: pre-accept both Agreements for vendor_user_a (the primary
    # seeded contact everything else in this script, and the E2E vertical
    # slice, already assumes can submit a proposal immediately) so existing
    # demo flows are not newly blocked by a gate they never used to have to
    # clear. Deliberately NOT pre-accepted for vendor_user_a2 (the second
    # collaborator seeded above) - logging in as that actor is exactly how a
    # developer exercises the "each collaborator accepts individually"
    # behavior (ADR 0014) without writing a dedicated script for it.
    agreement_service = AgreementService(AgreementRepository(db))
    vendor_a_membership = next(m for m in created if m.user_id == vendor_user_a.id)
    for agreement_type in ("nda", "conflict_of_interest"):
        if not agreement_service.has_current_acceptance(
            tenant_a.id, vendor_user_a.id, agreement_type
        ):
            agreement_service.accept(
                tenant_a.id,
                vendor_user_a.id,
                vendor_a_membership.id,
                agreement_type,
                ip="127.0.0.1",
                user_agent="seed-dev",
            )

    evaluations = EvaluationRepository(db)
    proposals = ProposalRepository(db)
    _get_or_create_evaluation(
        evaluations,
        proposals,
        tenant_a,
        owner_a_membership,
        vendor_org_a,
        "Evaluacion de ejemplo (dev)",
    )

    # Fase 12: one evaluation per approval_status beyond "not_requested"
    # (already the state of "Evaluacion de ejemplo (dev)" above), so the
    # approval/publication UI has something to demo/QA against.
    for approval_state, name in [
        ("pending", "Evaluacion pendiente de aprobacion (dev)"),
        ("approved", "Evaluacion aprobada (dev)"),
        ("rejected", "Evaluacion rechazada (dev)"),
        ("published", "Evaluacion publicada (dev)"),
    ]:
        _get_or_create_evaluation_with_approval_state(
            settings,
            db,
            tenant_a,
            owner_a_membership,
            approver_a_membership,
            vendor_org_a,
            name,
            approval_state,
        )

    return created


def reset(settings: Settings) -> None:
    _require_dev_environment(settings)
    db = get_database(settings)
    for name in SEEDED_COLLECTIONS:
        db.drop_collection(name)


def _print_actor_table(settings: Settings, created: list[Membership]) -> None:
    db = get_database(settings)
    tenants = TenantRepository(db)
    users = UserRepository(db)
    print(f"{'actor_id (membership_id)':<34} {'display_name':<20} {'tenant':<26} role")
    for membership in created:
        tenant_doc = tenants.find_by_id(membership.tenant_id)
        user_doc = users.find_by_id(membership.user_id)
        tenant_name = tenant_doc["name"] if tenant_doc else membership.tenant_id
        display_name = user_doc["display_name"] if user_doc else membership.user_id
        print(f"{membership.id:<34} {display_name:<20} {tenant_name:<26} {membership.role}")


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    try:
        if "--reset" in sys.argv[1:]:
            reset(settings)
            logger.info("colecciones de seed-dev eliminadas: %s", ", ".join(SEEDED_COLLECTIONS))
            return
        created = seed(settings)
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)
    _print_actor_table(settings, created)


if __name__ == "__main__":
    main()
