import logging
import sys
from dataclasses import replace

from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.models import Membership, Role, Tenant, User, VendorOrganization
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


def _get_or_create_user(users: UserRepository, email: str, display_name: str) -> User:
    existing = users.find_by_email(email)
    if existing is not None:
        return User.from_document(existing)
    user = User.create(display_name=display_name, email=email)
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

    tenant_a = _get_or_create_tenant(tenants, "dev-tenant-a", "Acme Compradora (dev)")
    tenant_b = _get_or_create_tenant(tenants, "dev-tenant-b", "Globex Compradora (dev)")

    owner_a = _get_or_create_user(users, "owner.a@dev.procurawise.local", "Owner A")
    evaluator_a = _get_or_create_user(users, "evaluator.a@dev.procurawise.local", "Evaluator A")
    vendor_user_a = _get_or_create_user(users, "vendor.a@dev.procurawise.local", "Vendor Contact A")
    owner_b = _get_or_create_user(users, "owner.b@dev.procurawise.local", "Owner B")
    evaluator_b = _get_or_create_user(users, "evaluator.b@dev.procurawise.local", "Evaluator B")

    vendor_org_a = _get_or_create_vendor_org(vendor_orgs, tenant_a, "Proveedor Uno (dev)")

    owner_a_membership = _get_or_create_membership(
        memberships, tenant_a, owner_a, "evaluation_owner"
    )

    # owner_b also holds a second Membership (evaluator, same tenant) on
    # purpose: demonstrates that a single User can carry multiple Memberships,
    # which the domain model must support without restriction.
    created = [
        owner_a_membership,
        _get_or_create_membership(memberships, tenant_a, evaluator_a, "evaluator"),
        _get_or_create_membership(
            memberships, tenant_a, vendor_user_a, "vendor_contact", vendor_org_a.id
        ),
        _get_or_create_membership(memberships, tenant_b, owner_b, "evaluation_owner"),
        _get_or_create_membership(memberships, tenant_b, evaluator_b, "evaluator"),
        _get_or_create_membership(memberships, tenant_b, owner_b, "evaluator"),
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
