from pymongo.database import Database


def apply(db: Database) -> None:
    db["tenants"].create_index("slug", unique=True, name="uniq_tenant_slug")
    db["memberships"].create_index(
        [("tenant_id", 1), ("user_id", 1), ("role", 1), ("vendor_org_id", 1)],
        unique=True,
        name="uniq_membership_tenant_user_role_vendor",
    )
    db["vendor_organizations"].create_index("tenant_id", name="idx_vendor_org_tenant")
