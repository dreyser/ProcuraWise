// Mutator injected into every orval-generated call (see orval.config.ts
// override.mutator). This is the single place that attaches identity
// headers - no component or feature hook may set them directly.
//
// Three mechanisms coexist here:
// `activeMembershipId` is the interim dev-header mechanism, kept only for
// /dev/actors + /me + local devtools exploration (actor/ActorContext.tsx) -
// no production route accepts it anymore (vendor_portal stopped accepting
// it in Fase 15, mirroring what AUTH-PROD already did to buyer routes).
// `activeAccessToken` is the buyer's real JWT (auth/AuthContext.tsx);
// `activeVendorAccessToken` is the vendor's real JWT (Fase 15,
// vendor-auth/VendorAuthContext.tsx). The two real tokens are kept in
// separate variables (not one shared slot) so a buyer login and a vendor
// login can never silently clobber each other's token if both happened to
// be exercised in the same browser tab/session - each login path clears the
// other's slot defensively (see setActiveAccessToken/
// setActiveVendorAccessToken call sites).
let activeMembershipId: string | null = null
let activeAccessToken: string | null = null
let activeVendorAccessToken: string | null = null

export function setActiveMembershipId(membershipId: string | null): void {
  activeMembershipId = membershipId
}

/** Never persisted (no localStorage/sessionStorage/cookies) - a page refresh
 * always loses it, forcing a real relogin (AUTH-PROD scope decision #2). */
export function setActiveAccessToken(token: string | null): void {
  activeAccessToken = token
}

/** Fase 15: the vendor-side mirror of setActiveAccessToken above - same
 * in-memory-only, no-persistence discipline (short TTL, no refresh token). */
export function setActiveVendorAccessToken(token: string | null): void {
  activeVendorAccessToken = token
}

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown
  /** Fase 13 (ai, ADR 0012): the adaptive polling controller reads
   * `Retry-After` off this to respect the server's backoff hint - optional
   * since most call sites never need it and older tests construct
   * ApiError(status, data) without a third argument. */
  readonly headers?: Headers

  constructor(status: number, data: unknown, headers?: Headers) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.headers = headers
  }
}

/**
 * Every orval-generated response type is a union of its declared success and
 * error status variants (e.g. `{data: T, status: 200} | {data: Error, status: 422}`),
 * because that's what the OpenAPI spec declares - but `apiFetch` above
 * throws for any non-2xx response, so a *resolved* value can only ever be
 * the success member at runtime. These narrow to that success member
 * explicitly instead of scattering `as` casts through every feature.
 */
export function unwrapData<TSuccess>(
  envelope: { data: TSuccess } | { data: unknown } | undefined,
): TSuccess | undefined {
  return envelope?.data as TSuccess | undefined
}

export function unwrapDataOrThrow<TSuccess>(
  envelope: { data: TSuccess } | { data: unknown },
): TSuccess {
  return envelope.data as TSuccess
}

export async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (activeMembershipId) {
    headers.set('X-Dev-Membership-Id', activeMembershipId)
  }
  // Only applied if the caller didn't already set one explicitly - the
  // pre-session-token calls in auth/AuthContext.tsx (GET /auth/memberships,
  // POST /auth/switch-tenant) pass their own Authorization header via
  // `options`, which must win over whatever access token (if any) is
  // already active from a previous session. Buyer and vendor tokens are
  // mutually exclusive in practice (each login path clears the other), so
  // whichever one is set is the request's real identity.
  const bearerToken = activeAccessToken ?? activeVendorAccessToken
  if (bearerToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${bearerToken}`)
  }

  const response = await fetch(url, { ...options, headers })
  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json')
    ? await response.json().catch(() => undefined)
    : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, data, response.headers)
  }

  return { status: response.status, data, headers: response.headers } as T
}
