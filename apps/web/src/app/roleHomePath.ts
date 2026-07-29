export function roleHomePath(role: string): string {
  return role === 'vendor_contact' ? '/vendor/proposals' : '/evaluations'
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
