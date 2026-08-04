import { useParams } from 'react-router-dom'
import {
  useGetTcoResultApiV1EvaluationsEvaluationIdProposalsProposalIdTcoGet,
  type TcoResultResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { normalizeApiError } from '@/lib/errors'

/** Fase 19 - the TCO frozen at submit time (plan §11.7). Read-only: the
 * comprador can never edit a vendor's costs, only see the deterministic
 * result the backend already calculated. */
export function TcoResultPage() {
  const { evaluationId, proposalId } = useParams<{ evaluationId: string; proposalId: string }>()

  const tcoQuery = useGetTcoResultApiV1EvaluationsEvaluationIdProposalsProposalIdTcoGet(
    evaluationId!,
    proposalId!,
  )
  const tco = unwrapData<TcoResultResponse>(tcoQuery.data)

  if (tcoQuery.isLoading) return <LoadingState label="Cargando TCO…" />
  if (tcoQuery.error instanceof ApiError && tcoQuery.error.status === 404) {
    return (
      <ErrorBanner message="El TCO de esta propuesta aún no está disponible (la propuesta debe estar enviada)." />
    )
  }
  if (tcoQuery.error) return <ErrorBanner message={normalizeApiError(tcoQuery.error).message} />
  if (!tco) return null

  const years = Object.keys(tco.by_year)
    .map(Number)
    .sort((a, b) => a - b)

  return (
    <div>
      <h1 className="text-lg font-semibold text-foreground">
        TCO ({tco.horizon_years} año(s), {tco.base_currency})
      </h1>

      <div className="mt-4 overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Año</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Total con impuestos</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {years.map((year) => (
              <TableRow key={year}>
                <TableCell>{year}</TableCell>
                <TableCell>{tco.by_year[String(year)]}</TableCell>
                <TableCell>{tco.by_year_with_tax[String(year)]}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-6 overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Categoría</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(tco.by_category).map(([category, total]) => (
              <TableRow key={category}>
                <TableCell>{category}</TableCell>
                <TableCell>{total}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-6 flex flex-wrap gap-6 text-sm">
        <p>
          <span className="text-muted-foreground">Total: </span>
          <span className="font-semibold text-foreground">{tco.grand_total}</span>
        </p>
        <p>
          <span className="text-muted-foreground">Total con impuestos: </span>
          <span className="font-semibold text-foreground">{tco.grand_total_with_tax}</span>
        </p>
      </div>

      {tco.fx_rates_used.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Tasas de cambio congeladas</h2>
          <ul className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
            {tco.fx_rates_used.map((rate, i) => (
              <li key={i}>
                {rate.from_currency} → {rate.to_currency}: {rate.rate} (vigente desde{' '}
                {rate.effective_date})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
