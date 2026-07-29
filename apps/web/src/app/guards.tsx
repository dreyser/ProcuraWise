import { type ReactElement } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useActor } from '@/actor/ActorContext'

/** Deep link without an active actor: redirect to the selector, preserving
 * the destination via ?next= (brief §10). Route guards are UX only - real
 * authorization always happens on the backend (brief §27). */
export function RequireActor({ children }: { children: ReactElement }) {
  const { status } = useActor()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground" role="status">
          Cargando…
        </p>
      </div>
    )
  }

  if (status === 'anonymous') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/dev/select-actor?next=${next}`} replace />
  }

  return children
}

export function RequireRole({ roles, children }: { roles: string[]; children: ReactElement }) {
  const { actor } = useActor()
  if (!actor) return null
  if (!roles.includes(actor.role)) {
    return <Navigate to="/unauthorized" replace />
  }
  return children
}
