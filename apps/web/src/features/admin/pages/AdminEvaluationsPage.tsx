import { useState } from 'react'
import {
  useListEvaluationsAcrossTenantsApiV1AdminEvaluationsGet,
  type AdminEvaluationListResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
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
import { CrossTenantReasonGate } from '@/features/admin/components/CrossTenantReasonGate'

/** platform_admin console - cross-tenant evaluations (Fase 9 backend,
 * Fase 25 Bloque 4 first-ever frontend consumer, plan Bloqueante #2 Opcion
 * b). Read-only: no admin write action exists in this phase. */
export function AdminEvaluationsPage() {
  const [reason, setReason] = useState<string | null>(null)

  const listQuery = useListEvaluationsAcrossTenantsApiV1AdminEvaluationsGet(
    { reason: reason ?? '', limit: 100 },
    { query: { enabled: reason !== null } },
  )
  const evaluations = unwrapData<AdminEvaluationListResponse>(listQuery.data)?.items ?? []

  return (
    <div className="max-w-4xl">
      <h1 className="text-lg font-semibold text-foreground">Evaluaciones (todas las empresas)</h1>

      <section className="mt-6">
        <CrossTenantReasonGate confirmedReason={reason} onConfirm={setReason} />
      </section>

      {reason !== null && (
        <section className="mt-6">
          {listQuery.isLoading ? (
            <LoadingState label="Consultando…" />
          ) : listQuery.error ? (
            <ErrorBanner message={normalizeApiError(listQuery.error).message} />
          ) : evaluations.length === 0 ? (
            <EmptyState title="Sin resultados" description="No hay evaluaciones registradas." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Empresa</TableHead>
                    <TableHead>Evaluación</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Creada</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {evaluations.map((evaluation) => (
                    <TableRow key={evaluation.id}>
                      <TableCell>{evaluation.tenant_name}</TableCell>
                      <TableCell>{evaluation.name}</TableCell>
                      <TableCell>
                        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
                      </TableCell>
                      <TableCell>{new Date(evaluation.created_at).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
