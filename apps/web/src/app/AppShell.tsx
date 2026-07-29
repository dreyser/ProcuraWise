import { type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useActor } from '@/actor/ActorContext'
import { translateRole } from '@/lib/enumLabels'

interface NavItem {
  to: string
  label: string
}

const BUYER_NAV: NavItem[] = [{ to: '/evaluations', label: 'Evaluaciones' }]

const VENDOR_NAV: NavItem[] = [{ to: '/vendor/proposals', label: 'Mis propuestas' }]

function navItemsForRole(role: string): NavItem[] {
  return role === 'vendor_contact' ? VENDOR_NAV : BUYER_NAV
}

export function AppShell({ children }: { children: ReactNode }) {
  const { actor, clearActor } = useActor()
  const navigate = useNavigate()

  if (!actor) return null

  const handleChangeActor = () => {
    clearActor()
    navigate('/dev/select-actor', { replace: true })
  }

  return (
    <div className="min-h-screen bg-background">
      <div
        role="status"
        className="border-b border-amber-300 bg-amber-50 px-4 py-1 text-center text-xs font-medium text-amber-900"
      >
        Modo de desarrollo — identidad seleccionada manualmente, no hay autenticación real
      </div>
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-3">
        <div>
          <p className="text-sm font-semibold text-foreground">ProcuraWise</p>
          <p className="text-xs text-muted-foreground">
            {actor.tenant_name} · {actor.display_name} · {translateRole(actor.role)}
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
        <button
          type="button"
          onClick={handleChangeActor}
          className="text-xs text-muted-foreground underline hover:text-foreground"
        >
          Cambiar de actor
        </button>
      </header>
      <main className="px-6 py-6">{children}</main>
    </div>
  )
}
