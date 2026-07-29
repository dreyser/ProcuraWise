import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { createAppQueryClient } from '@/lib/queryClient'
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

export function ActorProvider({ children }: { children: ReactNode }) {
  const [queryClient, setQueryClient] = useState<QueryClient>(() => createAppQueryClient())
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

  const selectActor = async (membershipId: string): Promise<SelectActorResult> => {
    setActiveMembershipId(membershipId)
    try {
      const response = await getMeApiV1MeGet()
      if (response.status !== 200) throw new Error('unexpected /me response')
      sessionStorage.setItem(STORAGE_KEY, membershipId)
      setActor(response.data)
      setStatus('ready')
      setQueryClient(createAppQueryClient())
      return { ok: true }
    } catch (error) {
      setActiveMembershipId(null)
      if (error instanceof ApiError && error.status === 401) {
        return { ok: false, message: 'Ese actor de desarrollo ya no es válido.' }
      }
      return { ok: false, message: 'No se pudo seleccionar el actor. Intenta de nuevo.' }
    }
  }

  const clearActor = () => {
    sessionStorage.removeItem(STORAGE_KEY)
    setActiveMembershipId(null)
    setActor(null)
    setStatus('anonymous')
    setQueryClient(createAppQueryClient())
  }

  const value = useMemo<ActorContextValue>(
    () => ({ actor, status, selectActor, clearActor }),
    [actor, status],
  )

  return (
    <QueryClientProvider client={queryClient}>
      <ActorReactContext.Provider value={value}>{children}</ActorReactContext.Provider>
    </QueryClientProvider>
  )
}

export function useActor(): ActorContextValue {
  const ctx = useContext(ActorReactContext)
  if (!ctx) {
    throw new Error('useActor debe usarse dentro de <ActorProvider>')
  }
  return ctx
}
