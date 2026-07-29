import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { setActiveMembershipId, ApiError } from '@/lib/http'
import { getMeApiV1MeGet, type ActorContextResponse } from '@/api/client'

const STORAGE_KEY = 'procurawise.dev.membershipId'

export type ActorStatus = 'loading' | 'ready' | 'anonymous'

export interface SelectActorResult {
  ok: boolean
  message?: string
}

interface ActorContextValue {
  actor: ActorContextResponse | null
  status: ActorStatus
  selectActor: (membershipId: string) => Promise<SelectActorResult>
  clearActor: () => void
}

const ActorReactContext = createContext<ActorContextValue | null>(null)

/**
 * Interim dev-header identity mechanism (`X-Dev-Membership-Id`) - kept after
 * AUTH-PROD as the vendor_contact mechanism until Fase 15 delivers real
 * invitation-token auth for vendors (AUTH-PROD scope decision #1). Buyer
 * routes use `auth/AuthContext.tsx` instead, mounted alongside this provider
 * (not in place of it) in App.tsx - each governs a physically separate route
 * tree (VendorLayout vs BuyerLayout in app/router.tsx).
 *
 * Requires a `QueryClientProvider` ancestor (App.tsx) - this no longer
 * creates its own, it shares the single app-wide QueryClient via
 * useQueryClient() so a buyer login/logout and a vendor actor switch can
 * never each hold their own client and disagree about whose cache is
 * "current".
 */
export function ActorProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [actor, setActor] = useState<ActorContextResponse | null>(null)
  const [status, setStatus] = useState<ActorStatus>('loading')

  useEffect(() => {
    const storedId = sessionStorage.getItem(STORAGE_KEY)
    if (!storedId) {
      setStatus('anonymous')
      return
    }

    setActiveMembershipId(storedId)
    getMeApiV1MeGet()
      .then((response) => {
        if (response.status !== 200) throw new Error('unexpected /me response')
        setActor(response.data)
        setStatus('ready')
      })
      .catch(() => {
        sessionStorage.removeItem(STORAGE_KEY)
        setActiveMembershipId(null)
        setStatus('anonymous')
      })
    // Runs once on mount to rehydrate a refreshed page - actor switches are
    // handled explicitly by selectActor/clearActor below, not by this effect.
  }, [])

  const selectActor = useCallback(
    async (membershipId: string): Promise<SelectActorResult> => {
      setActiveMembershipId(membershipId)
      try {
        const response = await getMeApiV1MeGet()
        if (response.status !== 200) throw new Error('unexpected /me response')
        sessionStorage.setItem(STORAGE_KEY, membershipId)
        setActor(response.data)
        setStatus('ready')
        queryClient.clear()
        return { ok: true }
      } catch (error) {
        setActiveMembershipId(null)
        if (error instanceof ApiError && error.status === 401) {
          return { ok: false, message: 'Ese actor de desarrollo ya no es válido.' }
        }
        return { ok: false, message: 'No se pudo seleccionar el actor. Intenta de nuevo.' }
      }
    },
    [queryClient],
  )

  const clearActor = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY)
    setActiveMembershipId(null)
    setActor(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const value = useMemo<ActorContextValue>(
    () => ({ actor, status, selectActor, clearActor }),
    [actor, status, selectActor, clearActor],
  )

  return <ActorReactContext.Provider value={value}>{children}</ActorReactContext.Provider>
}

export function useActor(): ActorContextValue {
  const ctx = useContext(ActorReactContext)
  if (!ctx) {
    throw new Error('useActor debe usarse dentro de <ActorProvider>')
  }
  return ctx
}
