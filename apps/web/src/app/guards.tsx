import { type ReactElement } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useActor } from '@/actor/ActorContext'
import { useAuth } from '@/auth/AuthContext'
import { useVendorAuth } from '@/vendor-auth/VendorAuthContext'
import { useAdminAuth } from '@/admin-auth/AdminAuthContext'

/** Deep link without an active vendor dev-actor: redirect to the interim
 * selector, preserving the destination via ?next=. Route guards are UX
 * only - real authorization always happens on the backend. */
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

/** Fase 15: vendor equivalent of RequireAuth below, backed by real vendor
 * auth (vendor-auth/VendorAuthContext) instead of the interim dev-header
 * mechanism RequireActor still guards. Redirects to /vendor/login,
 * preserving the destination via ?next= - never to /dev/select-actor,
 * which remains a devtools-only path with no production consumer left. */
export function RequireVendorAuth({ children }: { children: ReactElement }) {
  const { status } = useVendorAuth()
  const location = useLocation()

  if (status === 'anonymous') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/vendor/login?next=${next}`} replace />
  }

  return children
}

/** Fase 25: platform_admin equivalent of RequireVendorAuth above, backed by
 * real admin auth (admin-auth/AdminAuthContext). Redirects to /admin/login,
 * preserving the destination via ?next=. */
export function RequireAdminAuth({ children }: { children: ReactElement }) {
  const { status } = useAdminAuth()
  const location = useLocation()

  if (status === 'anonymous') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/admin/login?next=${next}`} replace />
  }

  return children
}

/** Buyer equivalent of RequireActor, backed by real auth (AUTH-PROD) instead
 * of the dev-header mechanism. Redirects to /login (anonymous) or
 * /auth/select-workspace (a login resolved to more than one Membership,
 * still awaiting a choice) - never to /dev/select-actor, which is the
 * vendor-only mechanism. */
export function RequireAuth({ children }: { children: ReactElement }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'anonymous') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  if (status === 'awaiting_workspace') {
    return <Navigate to="/auth/select-workspace" replace />
  }

  return children
}

/** Takes the resolved actor as a prop rather than reading a fixed hook - the
 * caller (BuyerLayout: auth/AuthContext; VendorLayout: actor/ActorContext)
 * decides which of the two identity mechanisms it belongs to. */
export function RequireRole({
  roles,
  actor,
  children,
}: {
  roles: string[]
  actor: { role: string } | null
  children: ReactElement
}) {
  if (!actor) return null
  if (!roles.includes(actor.role)) {
    return <Navigate to="/unauthorized" replace />
  }
  return children
}
