import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function CheckoutCancelledPage() {
  return (
    <div className="mx-auto max-w-xl p-8 text-center">
      <h1 className="text-lg font-semibold text-foreground">Pago cancelado</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        No se completó el pago. Puedes intentarlo de nuevo cuando quieras.
      </p>
      <Button asChild className="mt-4">
        <Link to="/billing">Volver a Facturación</Link>
      </Button>
    </div>
  )
}
