import { type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { translateRole } from '@/lib/enumLabels'

interface NavItem {
  to: string
  label: string
}

const BUYER_NAV: NavItem[] = [
  { to: '/evaluations', label: 'Evaluaciones' },
  { to: '/knowledge-templates', label: 'Plantillas' },
]

const VENDOR_NAV: NavItem[] = [{ to: '/vendor/proposals', label: 'Mis propuestas' }]

// Fase 25 (billing/admin, ADR 0025): tenant_admin's only area this phase -
// deliberately not merged into BUYER_NAV, since tenant_admin has no access
// to /evaluations or /knowledge-templates (BUYER_ROLES in app/router.tsx).
const TENANT_ADMIN_NAV: NavItem[] = [{ to: '/billing', label: 'Facturación' }]

// Fase 25 Bloque 4: platform_admin's console - read-only cross-tenant pages
// (plan Bloqueante #2 Opcion b), no dashboard/tenant-management/write
// actions in this phase.
const PLATFORM_ADMIN_NAV: NavItem[] = [
  { to: '/admin/evaluations', label: 'Evaluaciones' },
  { to: '/admin/billing', label: 'Facturación' },
]

function navItemsForRole(role: string): NavItem[] {
  if (role === 'vendor_contact') return VENDOR_NAV
  if (role === 'tenant_admin') return TENANT_ADMIN_NAV
  if (role === 'platform_admin') return PLATFORM_ADMIN_NAV
  return BUYER_NAV
}

interface AppShellActor {
  /** Fase 25: optional - platform_admin has no tenant at all (see
   * admin-auth/AdminAuthContext.tsx's AdminActor). */
  tenant_name?: string
  display_name: string
  role: string
}

interface AppShellProps {
  actor: AppShellActor
  exitLabel: string
  onExit: () => void
  /** True only for the vendor interim mechanism (RequireActor/ActorContext) -
   * buyer sessions are real auth, no banner needed. */
  devModeNotice?: boolean
  /** Fase 24: BuyerLayout/VendorLayout each inject their own bell
   * (BuyerNotificationsBell/VendorNotificationsBell) - AppShell stays
   * presentation-only and never imports useAuth/useVendorAuth itself,
   * mirroring how exitLabel/onExit are already injected per-layout. */
  notifications?: ReactNode
  children: ReactNode
}

/**
 * Presentation-only shell shared by BuyerLayout and VendorLayout
 * (app/router.tsx) - takes the resolved actor and an exit action as props
 * instead of reading a fixed identity hook, since the two layouts are backed
 * by two different mechanisms (auth/AuthContext vs actor/ActorContext,
 * AUTH-PROD scope decision #1).
 */
export function AppShell({
  actor,
  exitLabel,
  onExit,
  devModeNotice = false,
  notifications,
  children,
}: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      {devModeNotice && (
        <div
          role="status"
          className="border-b border-amber-300 bg-amber-50 px-4 py-1 text-center text-xs font-medium text-amber-900"
        >
          Modo de desarrollo — identidad seleccionada manualmente, no hay autenticación real
        </div>
      )}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-3">
        <div>
          <p className="text-sm font-semibold text-foreground">ProcuraWise</p>
          <p className="text-xs text-muted-foreground">
            {actor.tenant_name ? `${actor.tenant_name} · ` : ''}
            {actor.display_name} · {translateRole(actor.role)}
          </p>
        </div>
        <nav aria-label="Navegación principal" className="flex gap-4">
          {navItemsForRole(actor.role).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `text-sm ${isActive ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {notifications}
          <button
            type="button"
            onClick={onExit}
            className="text-xs text-muted-foreground underline hover:text-foreground"
          >
            {exitLabel}
          </button>
        </div>
      </header>
      <main className="px-6 py-6">{children}</main>
    </div>
  )
}
