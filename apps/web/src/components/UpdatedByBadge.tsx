/** Never shows the raw membership_id (brief §11/§27) - only whether the
 * viewer or someone else last touched it. Real name resolution is deferred
 * to a future users/RBAC phase; `/dev/actors` is not reused for this. */
export function UpdatedByBadge({
  updatedByMembershipId,
  viewerMembershipId,
}: {
  updatedByMembershipId: string
  viewerMembershipId: string | undefined
}) {
  const isSelf = updatedByMembershipId === viewerMembershipId
  return (
    <span className="text-xs text-muted-foreground">
      {isSelf ? 'Actualizado por ti' : 'Actualizado por otro evaluador'}
    </span>
  )
}
