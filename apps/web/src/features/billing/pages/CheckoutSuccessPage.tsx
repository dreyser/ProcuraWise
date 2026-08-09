import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
import { translatePurchaseStatus } from '@/lib/enumLabels'
import { usePurchaseStatus } from '@/features/billing/hooks/usePurchaseStatus'

/** Fase 25 (billing/admin, ADR 0025): the security-relevant page in this
 * phase's frontend. `?purchase_id=` is used only to know *what* to poll -
 * it is never itself treated as proof of payment. The "Pagado" state shown
 * here comes exclusively from GET /billing/purchases/{id}, which only ever
 * reflects the webhook-confirmed backend state (plan S13.6/S13.8). */
export function CheckoutSuccessPage() {
  const [searchParams] = useSearchParams()
  const purchaseId = searchParams.get('purchase_id')

  if (!purchaseId) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <ErrorBanner message="Falta el identificador de la compra." />
      </div>
    )
  }

  return <CheckoutSuccessPolling purchaseId={purchaseId} />
}

function CheckoutSuccessPolling({ purchaseId }: { purchaseId: string }) {
  const snapshot = usePurchaseStatus(purchaseId)
  const purchase = snapshot?.result ?? null
  const isConfirming = purchase === null || purchase.status === 'pending'

  return (
    <div className="mx-auto max-w-xl p-8 text-center">
      <h1 className="text-lg font-semibold text-foreground">
        {isConfirming ? 'Confirmando tu pago…' : 'Pago confirmado'}
      </h1>

      {isConfirming && (
        <div className="mt-4">
          <LoadingState label="Esperando la confirmación del pago…" />
          {snapshot?.stale && (
            <p className="mt-2 text-xs text-muted-foreground">
              El pago sigue procesándose; te avisaremos por correo cuando se confirme.
            </p>
          )}
        </div>
      )}

      {purchase && !isConfirming && (
        <div className="mt-4 flex flex-col items-center gap-3">
          <StatusBadge label={translatePurchaseStatus(purchase.status)} />
          {purchase.status === 'paid' && (
            <p className="text-sm text-muted-foreground">
              Tu pago para la evaluación fue confirmado exitosamente.
            </p>
          )}
          {purchase.status === 'expired' && (
            <p className="text-sm text-muted-foreground">
              La sesión de pago expiró antes de completarse. Intenta de nuevo desde Facturación.
            </p>
          )}
          <Button asChild>
            <Link to="/billing">Volver a Facturación</Link>
          </Button>
        </div>
      )}

      {snapshot?.error && (
        <div className="mt-4">
          <ErrorBanner message="No se pudo consultar el estado del pago. Intenta recargar." />
        </div>
      )}
    </div>
  )
}
