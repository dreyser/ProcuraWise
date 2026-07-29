import { Link } from 'react-router-dom'
import {
  useListProposalsApiV1VendorPortalProposalsGet,
  type VendorProposalSummaryResponse,
} from '@/api/client'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateProposalStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'

export function VendorProposalListPage() {
  const { data: response, isLoading, error } = useListProposalsApiV1VendorPortalProposalsGet()
  const proposals = unwrapData<VendorProposalSummaryResponse[]>(response)

  return (
    <div>
      <h1 className="text-lg font-semibold text-foreground">Mis propuestas</h1>

      <div className="mt-4">
        {isLoading && <LoadingState label="Cargando propuestas…" />}
        {error && <ErrorBanner message={normalizeApiError(error).message} />}
        {proposals && proposals.length === 0 && (
          <EmptyState
            title="Todavía no tienes propuestas"
            description="Cuando un comprador te vincule a una evaluación, aparecerá aquí."
          />
        )}
        {proposals && proposals.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Evaluación</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Última actualización</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((proposal) => (
                  <TableRow key={proposal.id}>
                    <TableCell>
                      <Link
                        to={`/vendor/proposals/${proposal.id}`}
                        className="font-medium text-foreground underline-offset-2 hover:underline"
                      >
                        {proposal.evaluation_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge label={translateProposalStatus(proposal.status)} />
                    </TableCell>
                    <TableCell>
                      {new Date(proposal.updated_at).toLocaleDateString('es-MX')}
                    </TableCell>
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
