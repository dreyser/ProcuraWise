import { Link } from 'react-router-dom'
import { useListEvaluationsApiV1EvaluationsGet, type EvaluationSummaryResponse } from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateEvaluationStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'

export function EvaluationListPage() {
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const { data: response, isLoading, error } = useListEvaluationsApiV1EvaluationsGet()
  const data = unwrapData<EvaluationSummaryResponse[]>(response)

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Evaluaciones</h1>
        {isOwner && (
          <Button asChild>
            <Link to="/evaluations/new">Nueva evaluación</Link>
          </Button>
        )}
      </div>

      <div className="mt-4">
        {isLoading && <LoadingState label="Cargando evaluaciones…" />}
        {error && <ErrorBanner message={normalizeApiError(error).message} />}
        {data && data.length === 0 && (
          <EmptyState
            title="Todavía no hay evaluaciones"
            description={
              isOwner
                ? 'Crea la primera evaluación para empezar.'
                : 'El responsable de evaluación aún no ha creado ninguna.'
            }
          />
        )}
        {data && data.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Proveedores vinculados</TableHead>
                  <TableHead>Última actualización</TableHead>
                  {isOwner && <TableHead>Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((evaluation) => (
                  <TableRow key={evaluation.id}>
                    <TableCell>
                      <Link
                        to={`/evaluations/${evaluation.id}`}
                        className="font-medium text-foreground underline-offset-2 hover:underline"
                      >
                        {evaluation.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
                    </TableCell>
                    <TableCell>{evaluation.linked_vendor_count} / 6</TableCell>
                    <TableCell>
                      {new Date(evaluation.updated_at).toLocaleDateString('es-MX')}
                    </TableCell>
                    {isOwner && (
                      <TableCell>
                        {evaluation.status === 'draft' && (
                          <Link
                            to={`/evaluations/${evaluation.id}/wizard`}
                            className="text-sm text-foreground underline-offset-2 hover:underline"
                          >
                            Continuar configuración
                          </Link>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  )
}
