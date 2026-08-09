import { useState } from 'react'
import {
  useCreateCheckoutSessionApiV1BillingCheckoutSessionsPost,
  useListPurchasesApiV1BillingPurchasesGet,
  type PurchaseListResponse,
  type PurchaseResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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

function formatAmount(amountTotal: number | null, currency: string | null): string {
  if (amountTotal === null || currency === null) return '—'
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: currency.toUpperCase(),
  }).format(amountTotal / 100)
}

/** "Facturación" - tenant_admin's first UI area (Fase 25, ADR 0025, plan
 * Bloqueante #1 Opcion A: one-time per-evaluation Checkout, no subscription).
 * tenant_admin has no access to /evaluations (BUYER_ROLES excludes it,
 * app/router.tsx) - the evaluation_id to pay for is relayed by the
 * evaluation_owner (who can see it, and who can read - but never create -
 * billing state for their own evaluation, per BILLING_READ_ROLES) rather
 * than browsed from a list this role cannot reach. */
export function BillingPage() {
  const [evaluationId, setEvaluationId] = useState('')

  const listQuery = useListPurchasesApiV1BillingPurchasesGet()
  const purchases = unwrapData<PurchaseListResponse>(listQuery.data)?.items ?? []

  const createCheckout = useCreateCheckoutSessionApiV1BillingCheckoutSessionsPost({
    mutation: {
      onSuccess: (response) => {
        const purchase = unwrapData<PurchaseResponse>(response)
        if (purchase) window.location.href = purchase.checkout_url
      },
    },
  })

  const handlePay = () => {
    const trimmed = evaluationId.trim()
    if (!trimmed) return
    createCheckout.mutate({ data: { evaluation_id: trimmed } })
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold text-foreground">Facturación</h1>

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">Nueva compra</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Pega el ID de la evaluación que el responsable de evaluación te compartió.
        </p>
        <div className="mt-3 flex flex-col gap-3 sm:max-w-md">
          <div>
            <Label htmlFor="evaluation-id-input">ID de la evaluación</Label>
            <Input
              id="evaluation-id-input"
              value={evaluationId}
              onChange={(event) => setEvaluationId(event.target.value)}
              placeholder="p. ej. 64f1a2b3c4d5e6f7a8b9c0d1"
            />
          </div>
          {createCheckout.isError && (
            <ErrorBanner message={normalizeApiError(createCheckout.error).message} />
          )}
          <Button
            type="button"
            className="self-start"
            disabled={!evaluationId.trim() || createCheckout.isPending}
            onClick={handlePay}
          >
            {createCheckout.isPending ? 'Redirigiendo…' : 'Pagar'}
          </Button>
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-foreground">Compras</h2>
        <div className="mt-3">
          {listQuery.isLoading ? (
            <LoadingState label="Cargando compras…" />
          ) : listQuery.error ? (
            <ErrorBanner message={normalizeApiError(listQuery.error).message} />
          ) : purchases.length === 0 ? (
            <EmptyState
              title="Sin compras"
              description="Todavía no se ha iniciado ninguna compra para este tenant."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Evaluación</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Monto</TableHead>
                    <TableHead>Creada</TableHead>
                    <TableHead>Fecha de pago</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {purchases.map((purchase) => (
                    <TableRow key={purchase.id}>
                      <TableCell className="font-mono text-xs">{purchase.evaluation_id}</TableCell>
                      <TableCell>
                        <StatusBadge label={translatePurchaseStatus(purchase.status)} />
                      </TableCell>
                      <TableCell>
                        {formatAmount(purchase.amount_total, purchase.currency)}
                      </TableCell>
                      <TableCell>{new Date(purchase.created_at).toLocaleString()}</TableCell>
                      <TableCell>
                        {purchase.paid_at ? new Date(purchase.paid_at).toLocaleString() : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
