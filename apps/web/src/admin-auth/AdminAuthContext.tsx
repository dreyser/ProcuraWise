import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { adminLoginApiV1AdminAuthLoginPost } from '@/api/client'
import {
  setActiveAdminAccessToken,
  setActiveAccessToken,
  setActiveVendorAccessToken,
  ApiError,
} from '@/lib/http'

export type AdminAuthStatus = 'anonymous' | 'ready'

export interface AdminAuthResult {
  ok: boolean
  message?: string
}

/** Deliberately NOT ActorContextResponse - platform_admin has no tenant_id
 * claim at all (backend: admin.context.PlatformAdminContext, never
 * shared.context.ActorContext), so its frontend actor shape mirrors that
 * split instead of reusing the buyer/vendor one. `role` is a literal
 * constant (not read off the response, which doesn't send one) purely so
 * this object satisfies AppShell's `{role: string}` actor contract. */
export interface AdminActor {
  admin_id: string
  display_name: string
  role: 'platform_admin'
}

interface AdminAuthContextValue {
  status: AdminAuthStatus
  actor: AdminActor | null
  loginWithPassword: (email: string, password: string) => Promise<AdminAuthResult>
  logout: () => void
}

const AdminAuthReactContext = createContext<AdminAuthContextValue | null>(null)

const GENERIC_ERROR = 'No se pudo continuar. Intenta de nuevo.'

/**
 * Fase 25 (billing/admin, ADR 0025): platform_admin's first frontend auth
 * area - email+password login backed by the backend's real admin JWT
 * (token_use=admin_access). Same in-memory-only, never-persisted token
 * discipline as buyer/vendor auth (a page refresh always starts anonymous
 * and requires a real relogin) - see auth/AuthContext.tsx and
 * vendor-auth/VendorAuthContext.tsx for the two precedents this mirrors.
 */
export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AdminAuthStatus>('anonymous')
  const [actor, setActor] = useState<AdminActor | null>(null)

  const loginWithPassword = useCallback(
    async (email: string, password: string): Promise<AdminAuthResult> => {
      let response
      try {
        response = await adminLoginApiV1AdminAuthLoginPost({ email, password })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return { ok: false, message: 'Correo o contraseña incorrectos.' }
        }
        return { ok: false, message: GENERIC_ERROR }
      }
      if (response.status !== 200) return { ok: false, message: GENERIC_ERROR }

      setActiveAdminAccessToken(response.data.access_token)
      // Defensive - an admin login always wins over any buyer or vendor
      // session that might still be active in this same tab.
      setActiveAccessToken(null)
      setActiveVendorAccessToken(null)
      setActor({
        admin_id: response.data.admin_id,
        display_name: response.data.display_name,
        role: 'platform_admin',
      })
      setStatus('ready')
      queryClient.clear()
      return { ok: true }
    },
    [queryClient],
  )

  const logout = useCallback(() => {
    setActiveAdminAccessToken(null)
    setActor(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const value = useMemo<AdminAuthContextValue>(
    () => ({ status, actor, loginWithPassword, logout }),
    [status, actor, loginWithPassword, logout],
  )

  return <AdminAuthReactContext.Provider value={value}>{children}</AdminAuthReactContext.Provider>
}

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthReactContext)
  if (!ctx) {
    throw new Error('useAdminAuth debe usarse dentro de <AdminAuthProvider>')
  }
  return ctx
}
