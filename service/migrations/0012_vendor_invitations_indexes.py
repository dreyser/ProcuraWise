from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 15: token_hash is looked up before a tenant is known (the
    # redemption request only carries the raw token) - same precedent as
    # `users.email` (migration 0003): a globally unique index, not prefixed
    # by tenant_id, because the lookup itself is what resolves the tenant.
    db["vendor_invitations"].create_index(
        "token_hash", unique=True, name="uniq_vendor_invitation_token_hash"
    )
    # Backs "list collaborators/invitations for this vendor organization"
    # (buyer-authenticated, tenant already known at that point).
    db["vendor_invitations"].create_index(
        [("tenant_id", 1), ("vendor_org_id", 1), ("status", 1)],
        name="idx_vendor_invitations_tenant_vendor_org_status",
    )
