import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { ErrorBanner } from '@/components/ErrorBanner'
import { translateRole } from '@/lib/enumLabels'
import { isNextPathAllowedForRole, roleHomePath } from '@/app/roleHomePath'

/** Shown only when a login (local or OIDC) resolves to more than one buyer
 * Membership - the real-auth successor to actor/SelectActorPage, but backed
 * by the authenticated user's own memberships (GET /auth/memberships) rather
 * than every dev-seeded actor in the database. */
export function SelectWorkspacePage() {
  const { memberships, selectWorkspace, status } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [selectionError, setSelectionError] = useState<string | null>(null)

  const handleSelect = async (membershipId: string, role: string) => {
    setPendingId(membershipId)
    setSelectionError(null)
    const result = await selectWorkspace(membershipId)
    setPendingId(null)
    if (!result.ok) {
      setSelectionError(result.message ?? 'No se pudo seleccionar el espacio de trabajo.')
      return
    }
    const next = searchParams.get('next')
    const destination = next && isNextPathAllowedForRole(next, role) ? next : roleHomePath(role)
    navigate(destination, { replace: true })
  }

  if (status !== 'awaiting_workspace' && memberships.length === 0) {
    return (
      <main className="mx-auto max-w-xl p-8">
        <ErrorBanner message="No hay un inicio de sesión en curso. Vuelve a iniciar sesión." />
        <a href="/login" className="mt-4 inline-block text-sm text-primary underline">
          Ir a iniciar sesión
        </a>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-lg font-semibold text-foreground">Elige un espacio de trabajo</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Tu cuenta tiene acceso a más de una organización. Elige con cuál continuar.
      </p>

      {selectionError && (
        <div className="mt-4">
          <ErrorBanner message={selectionError} />
        </div>
      )}

      <ul className="mt-6 flex flex-col gap-2">
        {memberships.map((membership) => (
          <li key={membership.membership_id}>
            <button
              type="button"
              onClick={() => handleSelect(membership.membership_id, membership.role)}
              disabled={pendingId !== null}
              className="flex w-full items-center justify-between rounded-md border border-border px-4 py-3 text-left hover:bg-accent disabled:opacity-50"
            >
              <span>
                <span className="block text-sm font-medium text-foreground">
                  {membership.tenant_name}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {translateRole(membership.role)}
                </span>
              </span>
              {pendingId === membership.membership_id && (
                <span className="text-xs text-muted-foreground">Entrando…</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </main>
  )
}
