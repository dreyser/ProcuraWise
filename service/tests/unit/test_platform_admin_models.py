from procurawise.admin.models import PlatformAdminAccount


def test_platform_admin_account_round_trips_through_document() -> None:
    account = PlatformAdminAccount.create(
        email="admin@example.com", display_name="Admin", password_hash="hash"
    )
    restored = PlatformAdminAccount.from_document(account.to_document())
    assert restored == account
