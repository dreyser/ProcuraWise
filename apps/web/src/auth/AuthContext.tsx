import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  loginApiV1AuthLoginPost,
  listMembershipsApiV1AuthMembershipsGet,
  switchTenantApiV1AuthSwitchTenantPost,
  type ActorContextResponse,
  type MembershipOption,
} from '@/api/client'
import {
  setActiveAccessToken,
  setActiveAdminAccessToken,
  setActiveVendorAccessToken,
  ApiError,
  resolveUrl,
} from '@/lib/http'

export type AuthStatus = 'anonymous' | 'awaiting_workspace' | 'ready'

export interface AuthResult {
  ok: boolean
  message?: string
  /** Fase 25: set only once a single Membership has actually resolved
   * (switchTenant's success path) - absent when login instead lands on
   * `awaiting_workspace` (RequireAuth redirects to /auth/select-workspace
   * on its own in that case, so callers don't need a role yet). Lets
   * LoginPage.tsx route to this actor's real home instead of assuming
   * every buyer role shares one (no longer true since tenant_admin,
   * Fase 25, has its own home at /billing). */
  role?: string
  /** Fase 28 (defecto real): set only when credentials were valid but the
   * account has zero buyer memberships - the one case where a real vendor
   * typing their own working credentials into the wrong (buyer) login form
   * hits a dead end with no indication of where to actually go. A typed
   * flag instead of matching on `message` text, since that string is
   * user-facing copy that should stay free to reword. */
  noBuyerAccess?: boolean
}

interface AuthContextValue {
  status: AuthStatus
  actor: ActorContextResponse | null
  memberships: MembershipOption[]
  loginWithPassword: (email: string, password: string) => Promise<AuthResult>
  beginOidcLogin: (provider: 'microsoft' | 'google') => void
  completeOidcCallback: (preSessionToken: string) => Promise<AuthResult>
  selectWorkspace: (membershipId: string) => Promise<AuthResult>
  logout: () => void
}

const AuthReactContext = createContext<AuthContextValue | null>(null)

const GENERIC_ERROR = 'No se pudo iniciar sesión. Intenta de nuevo.'

/**
 * Buyer authentication (AUTH-PROD): email+password or OIDC (Microsoft/Google),
 * backed by the backend's real JWT. Coexists in parallel with `actor/ActorContext`
 * (the interim dev-header mechanism vendor_contact still uses until Fase 15 -
 * see AUTH-PROD scope decision #1) - both providers are mounted together in
 * App.tsx, each governing a physically separate route tree (BuyerLayout vs
 * VendorLayout in app/router.tsx).
 *
 * No token is ever persisted (sessionStorage/localStorage/cookies) - a page
 * refresh always starts anonymous and requires a real relogin (scope
 * decision #2: short-lived JWT in memory, no refresh token).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthStatus>('anonymous')
  const [actor, setActor] = useState<ActorContextResponse | null>(null)
  const [memberships, setMemberships] = useState<MembershipOption[]>([])
  const [preSessionToken, setPreSessionToken] = useState<string | null>(null)

  // Fase 26 (Hardening): switchTenant is declared *before*
  // proceedFromPreSessionToken now (it was previously declared after, but
  // referenced from inside proceedFromPreSessionToken's closure with an
  // empty dependency array) - eslint-plugin-react-hooks 7 correctly flags
  // that as a real bug, not just a style nit: with `[]` as its deps,
  // proceedFromPreSessionToken's closure permanently freezes whichever
  // `switchTenant` existed at the very first render, which would go stale
  // if `switchTenant` were ever recreated (its own deps include
  // `queryClient` - stable today, but nothing guarantees that forever).
  // Declaring it first and listing it as a real dependency below removes
  // the forward reference entirely instead of relying on it never
  // mattering in practice.
  const switchTenant = useCallback(
    async (token: string, membershipId: string): Promise<AuthResult> => {
      let response
      try {
        response = await switchTenantApiV1AuthSwitchTenantPost(
          { membership_id: membershipId },
          { headers: { Authorization: `Bearer ${token}` } },
        )
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          return { ok: false, message: 'Ese espacio de trabajo ya no está disponible.' }
        }
        return { ok: false, message: GENERIC_ERROR }
      }
      if (response.status !== 200) return { ok: false, message: GENERIC_ERROR }

      setActiveAccessToken(response.data.access_token)
      // Fase 15/25: defensive - a buyer login always wins over any vendor
      // or admin session that might still be active in this same tab.
      setActiveVendorAccessToken(null)
      setActiveAdminAccessToken(null)
      setActor(response.data.actor)
      setPreSessionToken(null)
      setMemberships([])
      setStatus('ready')
      queryClient.clear()
      return { ok: true, role: response.data.actor.role }
    },
    [queryClient],
  )

  const proceedFromPreSessionToken = useCallback(
    async (token: string): Promise<AuthResult> => {
      let membershipsResponse
      try {
        membershipsResponse = await listMembershipsApiV1AuthMembershipsGet({
          headers: { Authorization: `Bearer ${token}` },
        })
      } catch {
        return { ok: false, message: GENERIC_ERROR }
      }
      if (membershipsResponse.status !== 200) return { ok: false, message: GENERIC_ERROR }

      const options = membershipsResponse.data.memberships
      if (options.length === 0) {
        return {
          ok: false,
          message:
            'Esta cuenta no tiene acceso de comprador. Si vas a entrar como proveedor, usa el portal de proveedores.',
          noBuyerAccess: true,
        }
      }
      if (options.length > 1) {
        setPreSessionToken(token)
        setMemberships(options)
        setStatus('awaiting_workspace')
        return { ok: true }
      }

      return switchTenant(token, options[0].membership_id)
    },
    [switchTenant],
  )

  const loginWithPassword = useCallback(
    async (email: string, password: string): Promise<AuthResult> => {
      let response
      try {
        response = await loginApiV1AuthLoginPost({ email, password })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return { ok: false, message: 'Correo o contraseña incorrectos.' }
        }
        return { ok: false, message: GENERIC_ERROR }
      }
      if (response.status !== 200) return { ok: false, message: GENERIC_ERROR }
      return proceedFromPreSessionToken(response.data.pre_session_token)
    },
    [proceedFromPreSessionToken],
  )

  const beginOidcLogin = useCallback((provider: 'microsoft' | 'google') => {
    // Fase 28: full-page navigation, not a fetch - never went through
    // apiFetch's own base-URL resolution, so it silently 404'd once the SPA
    // moved off the API's origin (resolved same-origin against the frontend
    // domain instead of the API's).
    window.location.href = resolveUrl(`/api/v1/auth/oidc/${provider}/login`)
  }, [])

  const completeOidcCallback = useCallback(
    (token: string) => proceedFromPreSessionToken(token),
    [proceedFromPreSessionToken],
  )

  const selectWorkspace = useCallback(
    async (membershipId: string): Promise<AuthResult> => {
      if (!preSessionToken) return { ok: false, message: GENERIC_ERROR }
      return switchTenant(preSessionToken, membershipId)
    },
    [preSessionToken, switchTenant],
  )

  const logout = useCallback(() => {
    setActiveAccessToken(null)
    setActor(null)
    setMemberships([])
    setPreSessionToken(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      actor,
      memberships,
      loginWithPassword,
      beginOidcLogin,
      completeOidcCallback,
      selectWorkspace,
      logout,
    }),
    [
      status,
      actor,
      memberships,
      loginWithPassword,
      beginOidcLogin,
      completeOidcCallback,
      selectWorkspace,
      logout,
    ],
  )

  return <AuthReactContext.Provider value={value}>{children}</AuthReactContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthReactContext)
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return ctx
}
