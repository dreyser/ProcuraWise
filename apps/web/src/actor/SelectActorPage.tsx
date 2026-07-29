import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useListDevActorsApiV1DevActorsGet } from '@/api/client'
import { ApiError } from '@/lib/http'
import { translateRole } from '@/lib/enumLabels'
import { useActor } from '@/actor/ActorContext'
import { isNextPathAllowedForRole, roleHomePath } from '@/app/roleHomePath'

export function SelectActorPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { selectActor } = useActor()
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [selectionError, setSelectionError] = useState<string | null>(null)

  const { data, isLoading, error } = useListDevActorsApiV1DevActorsGet()

  const isDevSelectorUnavailable = error instanceof ApiError && error.status === 404

  const handleSelect = async (actorId: string, role: string) => {
    setPendingId(actorId)
    setSelectionError(null)
    const result = await selectActor(actorId)
    setPendingId(null)
    if (!result.ok) {
      setSelectionError(result.message ?? 'No se pudo seleccionar el actor.')
      return
    }
    const next = searchParams.get('next')
    const destination = next && isNextPathAllowedForRole(next, role) ? next : roleHomePath(role)
    navigate(destination, { replace: true })
  }

  if (isDevSelectorUnavailable) {
    return (
      <main className="mx-auto max-w-xl p-8">
        <h1 className="text-lg font-semibold text-foreground">
          Selector de identidad de desarrollo no disponible
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Este mecanismo solo existe en entornos de desarrollo/pruebas. No es un error de la
          aplicación.
        </p>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <div className="mb-6 inline-flex items-center rounded-md border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900">
        Modo de desarrollo
      </div>
      <h1 className="text-lg font-semibold text-foreground">Selecciona un actor</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Elige la identidad (membership) con la que quieres explorar ProcuraWise.
      </p>

      {isLoading && (
        <p className="mt-6 text-sm text-muted-foreground" role="status">
          Cargando actores…
        </p>
      )}

      {Boolean(error) && !isDevSelectorUnavailable && (
        <p className="mt-6 text-sm text-destructive" role="alert">
          No se pudo cargar la lista de actores. Intenta de nuevo.
        </p>
      )}

      {selectionError && (
        <p className="mt-4 text-sm text-destructive" role="alert">
          {selectionError}
        </p>
      )}

      {data?.data && data.data.length === 0 && (
        <p className="mt-6 text-sm text-muted-foreground">
          No hay actores sembrados todavía. Corre <code>make seed-dev</code>.
        </p>
      )}

      <ul className="mt-6 flex flex-col gap-2">
        {data?.data.map((actor) => (
          <li key={actor.actor_id}>
            <button
              type="button"
              onClick={() => handleSelect(actor.actor_id, actor.role)}
              disabled={pendingId !== null}
              className="flex w-full items-center justify-between rounded-md border border-border px-4 py-3 text-left hover:bg-accent disabled:opacity-50"
            >
              <span>
                <span className="block text-sm font-medium text-foreground">
                  {actor.display_name}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {actor.tenant_name} · {translateRole(actor.role)}
                </span>
              </span>
              {pendingId === actor.actor_id && (
                <span className="text-xs text-muted-foreground">Entrando…</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </main>
  )
}
