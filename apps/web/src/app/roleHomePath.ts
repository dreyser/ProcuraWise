export function roleHomePath(role: string): string {
  if (role === 'vendor_contact') return '/vendor/proposals'
  // Fase 25 (billing/admin, ADR 0025): tenant_admin has no access to
  // /evaluations (BUYER_ROLES in app/router.tsx deliberately excludes it -
  // GET /evaluations 403s for this role on the backend too) - its only area
  // this phase is billing.
  if (role === 'tenant_admin') return '/billing'
  return '/evaluations'
}

/**
 * A `?next=` deep link can carry over from a previous, unrelated redirect
 * (e.g. a buyer route bounced through the selector before switching to a
 * vendor actor) - only honor it when it actually belongs to the newly
 * selected actor's area, otherwise fall back to that role's home.
 */
export function isNextPathAllowedForRole(next: string, role: string): boolean {
  const isVendorPath = next.startsWith('/vendor')
  return role === 'vendor_contact' ? isVendorPath : !isVendorPath
}
