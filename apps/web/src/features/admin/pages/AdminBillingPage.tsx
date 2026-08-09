import { useState } from 'react'
import {
  useListPurchasesAcrossTenantsApiV1AdminPurchasesGet,
  type AdminPurchaseListResponse,
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
import { translatePurchaseStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { CrossTenantReasonGate } from '@/features/admin/components/CrossTenantReasonGate'

function formatAmount(amountTotal: number | null, currency: string | null): string {
  if (amountTotal === null || currency === null) return '—'
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: currency.toUpperCase(),
  }).format(amountTotal / 100)
}

/** platform_admin console - cross-tenant billing (Fase 25 Bloque 4, plan
 * Bloqueante #2 Opcion b: the one new cross-tenant read this phase adds,
 * connecting the billing half with the admin half). Read-only. */
export function AdminBillingPage() {
  const [reason, setReason] = useState<string | null>(null)

  const listQuery = useListPurchasesAcrossTenantsApiV1AdminPurchasesGet(
    { reason: reason ?? '', limit: 100 },
    { query: { enabled: reason !== null } },
  )
  const purchases = unwrapData<AdminPurchaseListResponse>(listQuery.data)?.items ?? []

  return (
    <div className="max-w-4xl">
      <h1 className="text-lg font-semibold text-foreground">Facturación (todas las empresas)</h1>

      <section className="mt-6">
        <CrossTenantReasonGate confirmedReason={reason} onConfirm={setReason} />
      </section>

      {reason !== null && (
        <section className="mt-6">
          {listQuery.isLoading ? (
            <LoadingState label="Consultando…" />
          ) : listQuery.error ? (
            <ErrorBanner message={normalizeApiError(listQuery.error).message} />
          ) : purchases.length === 0 ? (
            <EmptyState title="Sin resultados" description="No hay compras registradas." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Empresa</TableHead>
                    <TableHead>Evaluación</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Monto</TableHead>
                    <TableHead>Creada</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {purchases.map((purchase) => (
                    <TableRow key={purchase.id}>
                      <TableCell>{purchase.tenant_name}</TableCell>
                      <TableCell className="font-mono text-xs">{purchase.evaluation_id}</TableCell>
                      <TableCell>
                        <StatusBadge label={translatePurchaseStatus(purchase.status)} />
                      </TableCell>
                      <TableCell>
                        {formatAmount(purchase.amount_total, purchase.currency)}
                      </TableCell>
                      <TableCell>{new Date(purchase.created_at).toLocaleString()}</TableCell>
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
