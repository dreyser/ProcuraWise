// Mutator injected into every orval-generated call (see orval.config.ts
// override.mutator). This is the single place that attaches the dev-actor
// header - no component or feature hook may set it directly.
let activeMembershipId: string | null = null

export function setActiveMembershipId(membershipId: string | null): void {
  activeMembershipId = membershipId
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
