// Mutator injected into every orval-generated call (see orval.config.ts
// override.mutator). This is the single place that attaches identity
// headers - no component or feature hook may set them directly.
//
// Four mechanisms coexist here:
// `activeMembershipId` is the interim dev-header mechanism, kept only for
// /dev/actors + /me + local devtools exploration (actor/ActorContext.tsx) -
// no production route accepts it anymore (vendor_portal stopped accepting
// it in Fase 15, mirroring what AUTH-PROD already did to buyer routes).
// `activeAccessToken` is the buyer's real JWT (auth/AuthContext.tsx);
// `activeVendorAccessToken` is the vendor's real JWT (Fase 15,
// vendor-auth/VendorAuthContext.tsx); `activeAdminAccessToken` is
// platform_admin's real JWT (Fase 25, admin-auth/AdminAuthContext.tsx,
// token_use=admin_access - structurally distinct from the buyer/vendor
// "access"/"vendor_access" tokens, see identity.jwt_provider). The three
// real tokens are kept in separate variables (not one shared slot) so a
// login as one actor type can never silently clobber another's token if
// more than one happened to be exercised in the same browser tab/session -
// each login path clears the other two slots defensively (see
// setActiveAccessToken/setActiveVendorAccessToken/
// setActiveAdminAccessToken call sites).
let activeMembershipId: string | null = null
let activeAccessToken: string | null = null
let activeVendorAccessToken: string | null = null
let activeAdminAccessToken: string | null = null

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

/** Fase 25: the platform_admin-side mirror of setActiveAccessToken above -
 * same in-memory-only, no-persistence discipline. */
export function setActiveAdminAccessToken(token: string | null): void {
  activeAdminAccessToken = token
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

/** Fase 28: every orval-generated call site passes a relative URL
 * (`/api/v1/...`) - resolved same-origin, which only works when the SPA and
 * the API share a domain (true in dev, via the Vite proxy in
 * vite.config.ts). Once the SPA is served from its own Container App
 * (staging/production), it needs an absolute origin instead; empty in dev/
 * test so local/CI behavior is unchanged. Exported because not every request
 * to the API goes through apiFetch - full-page navigations (OIDC login
 * kickoff, AuthContext.tsx) need the same origin resolution but issue a raw
 * `window.location.href` assignment instead of a fetch. */
export function resolveUrl(url: string): string {
  const base = import.meta.env.VITE_API_BASE_URL
  return base ? `${base}${url}` : url
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
  // already active from a previous session. Buyer, vendor, and admin
  // tokens are mutually exclusive in practice (each login path clears the
  // other two), so whichever one is set is the request's real identity.
  const bearerToken = activeAccessToken ?? activeVendorAccessToken ?? activeAdminAccessToken
  if (bearerToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${bearerToken}`)
  }

  const response = await fetch(resolveUrl(url), { ...options, headers })
  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json')
    ? await response.json().catch(() => undefined)
    : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, data, response.headers)
  }

  return { status: response.status, data, headers: response.headers } as T
}
