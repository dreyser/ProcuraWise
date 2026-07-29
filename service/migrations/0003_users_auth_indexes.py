from pymongo.database import Database


def apply(db: Database) -> None:
    db["users"].create_index("email", unique=True, name="uniq_user_email")
    # Multikey unique index over an embedded array field. A first attempt
    # without `sparse` broke on real Mongo: an empty oidc_identities array
    # indexes both subfields as a single {provider: null, subject: null} key
    # (not "no key at all", as might be assumed) - so any two users without a
    # linked identity collided on that null/null key. `sparse=True` excludes
    # documents where the indexed fields are missing (which is what an empty
    # array produces here), fixing it. Verified against real Mongo in
    # tests/integration/test_user_auth_indexes.py, not assumed twice.
    db["users"].create_index(
        [("oidc_identities.provider", 1), ("oidc_identities.subject", 1)],
        unique=True,
        sparse=True,
        name="uniq_user_oidc_identity",
    )
