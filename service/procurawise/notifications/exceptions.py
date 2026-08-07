class NotificationNotFoundError(Exception):
    """No Notification exists for this id, within the caller's tenant, owned
    by the caller's own membership_id - collapses "does not exist",
    "belongs to another tenant", and "belongs to another recipient in the
    same tenant" into the same 404, never confirming which case applies."""
