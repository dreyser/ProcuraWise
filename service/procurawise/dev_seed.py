import logging
import sys
from dataclasses import replace

from procurawise.admin.models import PlatformAdminAccount
from procurawise.admin.repository import PlatformAdminAccountRepository
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.models import Membership, Role, Tenant, User, VendorOrganization
from procurawise.identity.passwords import hash_password
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.config import Settings, get_settings
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
    # POST /auth/login is exercisable without real OIDC apps. vendor_user_a
    # stays without one - the vendor portal keeps using the interim dev-header
    # mechanism (X-Dev-Membership-Id) until Fase 15, not real login.
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
    vendor_user_a = _get_or_create_user(users, "vendor.a@dev.procurawise.local", "Vendor Contact A")
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
        _get_or_create_membership(memberships, tenant_a, approver_a, "approver"),
        _get_or_create_membership(memberships, tenant_a, tenant_admin_a, "tenant_admin"),
        _get_or_create_membership(
            memberships, tenant_a, vendor_user_a, "vendor_contact", vendor_org_a.id
        ),
        _get_or_create_membership(memberships, tenant_b, owner_b, "evaluation_owner"),
        _get_or_create_membership(
            memberships, tenant_b, evaluator_technical_b, "evaluator_technical"
        ),
        _get_or_create_membership(memberships, tenant_b, owner_b, "approver"),
    ]

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
