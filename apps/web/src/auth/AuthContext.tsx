import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  loginApiV1AuthLoginPost,
  listMembershipsApiV1AuthMembershipsGet,
  switchTenantApiV1AuthSwitchTenantPost,
  type ActorContextResponse,
  type MembershipOption,
} from '@/api/client'
import { setActiveAccessToken, setActiveVendorAccessToken, ApiError } from '@/lib/http'

export type AuthStatus = 'anonymous' | 'awaiting_workspace' | 'ready'

export interface AuthResult {
  ok: boolean
  message?: string
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
          message: 'Tu cuenta no tiene accesos de comprador configurados todavía.',
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

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
      // Fase 15: defensive - a buyer login always wins over any vendor
      // session that might still be active in this same tab.
      setActiveVendorAccessToken(null)
      setActor(response.data.actor)
      setPreSessionToken(null)
      setMemberships([])
      setStatus('ready')
      queryClient.clear()
      return { ok: true }
    },
    [queryClient],
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
    window.location.href = `/api/v1/auth/oidc/${provider}/login`
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
