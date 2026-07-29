// Mutator injected into every orval-generated call (see orval.config.ts
// override.mutator). This is the single place that attaches identity
// headers - no component or feature hook may set them directly.
//
// Two independent mechanisms coexist here (AUTH-PROD scope decision #1):
// `activeMembershipId` is the interim dev-header mechanism vendor_contact
// still uses (actor/ActorContext.tsx); `activeAccessToken` is the real JWT
// buyer routes require (auth/AuthContext.tsx). They never apply to the same
// request in practice - buyer and vendor routers are physically disjoint -
// so both can be attached unconditionally without conflict.
let activeMembershipId: string | null = null
let activeAccessToken: string | null = null

export function setActiveMembershipId(membershipId: string | null): void {
  activeMembershipId = membershipId
}

/** Never persisted (no localStorage/sessionStorage/cookies) - a page refresh
 * always loses it, forcing a real relogin (AUTH-PROD scope decision #2). */
export function setActiveAccessToken(token: string | null): void {
  activeAccessToken = token
}

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown

  constructor(status: number, data: unknown) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
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
  // already active from a previous session.
  if (activeAccessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${activeAccessToken}`)
  }

  const response = await fetch(url, { ...options, headers })
  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json')
    ? await response.json().catch(() => undefined)
    : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, data)
  }

  return { status: response.status, data, headers: response.headers } as T
}
