from pymongo.database import Database


def apply(db: Database) -> None:
    db["platform_admins"].create_index("email", unique=True, name="uniq_platform_admin_email")
