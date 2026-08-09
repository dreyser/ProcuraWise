"""Centralized buyer-side role groupings (Fase 9, RBAC completo).

Before this phase, every buyer router (evaluations/scoring/proposals/audit/
identity) copy-pasted its own `BUYER_READ_ROLES`/`OWNER_ONLY` tuples. As the
role set grows from 3 to 7 (spec §4), that duplication becomes a real risk of
one router silently falling out of sync - this module is the single source of
truth instead.
"""

EVALUATOR_ROLES: tuple[str, ...] = (
    "evaluator_functional",
    "evaluator_technical",
    "evaluator_economic",
)

# Roles that may read/participate inside a specific evaluation. Mutation of
# evaluation structure (requirements, vendor links, lifecycle transitions)
# stays owner-only - see OWNER_ONLY below.
BUYER_READ_ROLES: tuple[str, ...] = (
    "evaluation_owner",
    *EVALUATOR_ROLES,
    "internal_collaborator",
    "approver",
)

OWNER_ONLY: tuple[str, ...] = ("evaluation_owner",)

# Scoring is a narrower write than general evaluation read: internal_collaborator
# ("sin autoridad final") and approver ("aprueba... dejando justificación") are
# in BUYER_READ_ROLES so they can review an evaluation, but neither actually
# scores requirements per spec §4 - only the owner and the three evaluator
# sub-roles do. Kept separate so scoring/router.py doesn't silently inherit a
# future widening of BUYER_READ_ROLES.
SCORE_WRITE_ROLES: tuple[str, ...] = ("evaluation_owner", *EVALUATOR_ROLES)

# GET /org/members (spec §4: "Administrador del cliente: Usuarios, roles").
# evaluation_owner also needs it, narrowly, to pick which evaluator
# Membership to assign to a section (spec: "Dueño de evaluación: ...
# coordina") - it does not grant evaluation_owner anything else tenant_admin
# can do.
ORG_MEMBERS_READ_ROLES: tuple[str, ...] = ("tenant_admin", "evaluation_owner")

# Every tenant-scoped buyer role that may authenticate with a real JWT via
# /api/v1/auth/* (AUTH-PROD). `vendor_contact` stays on the interim dev-header
# mechanism until Fase 15 (see vendor_portal/router.py); `platform_admin` has
# no tenant_id claim and is not a Membership at all (see procurawise.admin,
# Fase 9 Block 4) - both are deliberately excluded here.
BUYER_LOGIN_ROLES: tuple[str, ...] = (
    "evaluation_owner",
    *EVALUATOR_ROLES,
    "internal_collaborator",
    "approver",
    "tenant_admin",
)

# Which evaluator sub-role may be Assignment-bound to which Dimension
# (procurawise.assignments). `evaluations.models.Dimension` currently only
# defines "functional"/"technical" (VS-2B scope note) - "economic" arrives
# with real economic scoring in Fase 19-20, so evaluator_economic cannot be
# assigned to anything yet even though the role itself already exists.
# Fase 25 (billing/admin, ADR 0025, plan Bloqueante #1 Opcion A): write is
# tenant_admin-only (least privilege - an evaluator must never be able to
# create a real charge); evaluation_owner additionally gets read, so the
# person running the RFP can see its own payment state without needing
# tenant_admin themselves. Neither role is named explicitly for "pagos" by
# spec S4 (which assigns "planes/límites" to platform_admin and "usuarios/
# roles/configuración" to tenant_admin) - tenant_admin is the only
# defensible tenant-side choice for initiating a real charge.
BILLING_WRITE_ROLES: tuple[str, ...] = ("tenant_admin",)
BILLING_READ_ROLES: tuple[str, ...] = ("tenant_admin", "evaluation_owner")

EVALUATOR_ROLE_BY_DIMENSION: dict[str, str] = {
    "functional": "evaluator_functional",
    "technical": "evaluator_technical",
    "economic": "evaluator_economic",
}
