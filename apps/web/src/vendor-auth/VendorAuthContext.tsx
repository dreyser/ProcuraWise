import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  acceptInvitationApiV1VendorAuthAcceptInvitationPost,
  vendorLoginApiV1VendorAuthLoginPost,
  type ActorContextResponse,
} from '@/api/client'
import { setActiveVendorAccessToken, setActiveAccessToken, ApiError } from '@/lib/http'

export type VendorAuthStatus = 'anonymous' | 'ready'

export interface VendorAuthResult {
  ok: boolean
  message?: string
}

interface VendorAuthContextValue {
  status: VendorAuthStatus
  actor: ActorContextResponse | null
  loginWithPassword: (email: string, password: string) => Promise<VendorAuthResult>
  acceptInvitation: (token: string, password: string) => Promise<VendorAuthResult>
  logout: () => void
}

const VendorAuthReactContext = createContext<VendorAuthContextValue | null>(null)

const GENERIC_ERROR = 'No se pudo continuar. Intenta de nuevo.'

/**
 * Real vendor_contact authentication (Fase 15): email+password login or
 * invitation-token redemption, backed by the backend's real vendor JWT
 * (token_use=vendor_access). Replaces the interim dev-header mechanism
 * (actor/ActorContext.tsx) as the production path for VendorLayout - that
 * module is left in place unchanged (still backs /dev/actors + /me for
 * local devtools exploration), it is simply no longer wired into vendor
 * routing.
 *
 * No token is ever persisted (sessionStorage/localStorage/cookies) - same
 * short-lived-JWT-in-memory-only discipline as buyer auth (auth/
 * AuthContext.tsx): a page refresh always starts anonymous and requires a
 * real relogin.
 */
export function VendorAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<VendorAuthStatus>('anonymous')
  const [actor, setActor] = useState<ActorContextResponse | null>(null)

  const applySuccessfulToken = useCallback(
    (accessToken: string, nextActor: ActorContextResponse) => {
      setActiveVendorAccessToken(accessToken)
      // Fase 15: defensive - a vendor login always wins over any buyer
      // session that might still be active in this same tab.
      setActiveAccessToken(null)
      setActor(nextActor)
      setStatus('ready')
      queryClient.clear()
    },
    [queryClient],
  )

  const loginWithPassword = useCallback(
    async (email: string, password: string): Promise<VendorAuthResult> => {
      let response
      try {
        response = await vendorLoginApiV1VendorAuthLoginPost({ email, password })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return { ok: false, message: 'Correo o contraseña incorrectos.' }
        }
        return { ok: false, message: GENERIC_ERROR }
      }
      if (response.status !== 200) return { ok: false, message: GENERIC_ERROR }
      applySuccessfulToken(response.data.access_token, response.data.actor)
      return { ok: true }
    },
    [applySuccessfulToken],
  )

  const acceptInvitation = useCallback(
    async (token: string, password: string): Promise<VendorAuthResult> => {
      let response
      try {
        response = await acceptInvitationApiV1VendorAuthAcceptInvitationPost({ token, password })
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return {
            ok: false,
            message: 'Esta invitación ya no es válida. Pide al comprador que envíe una nueva.',
          }
        }
        return { ok: false, message: GENERIC_ERROR }
      }
      if (response.status !== 200) return { ok: false, message: GENERIC_ERROR }
      applySuccessfulToken(response.data.access_token, response.data.actor)
      return { ok: true }
    },
    [applySuccessfulToken],
  )

  const logout = useCallback(() => {
    setActiveVendorAccessToken(null)
    setActor(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const value = useMemo<VendorAuthContextValue>(
    () => ({ status, actor, loginWithPassword, acceptInvitation, logout }),
    [status, actor, loginWithPassword, acceptInvitation, logout],
  )

  return <VendorAuthReactContext.Provider value={value}>{children}</VendorAuthReactContext.Provider>
}

export function useVendorAuth(): VendorAuthContextValue {
  const ctx = useContext(VendorAuthReactContext)
  if (!ctx) {
    throw new Error('useVendorAuth debe usarse dentro de <VendorAuthProvider>')
  }
  return ctx
}
