import { useParams } from 'react-router-dom'
import {
  useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet,
  type AnswerResponse,
  type ProposalDetailResponse,
  type SnapshotCostItemResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { StatusBadge } from '@/components/StatusBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateAnswerStatus, translateCostItemStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'

function formatAnswerValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Fase 21 (ADR 0013, plan §12.7/R10): no dedicated diff endpoint - this
 * page reads the full snapshots[] history already returned by
 * GET .../proposals/{id} and computes the Ronda 0 vs Ronda 1 diff
 * client-side. Only reachable once a proposal has gone through exactly one
 * reopen (2 snapshots) - the MVP caps negotiation at a single round. */
export function ProposalVersionComparisonPage() {
  const { evaluationId, proposalId } = useParams<{ evaluationId: string; proposalId: string }>()

  const proposalQuery = useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet(
    evaluationId!,
    proposalId!,
  )
  const proposal = unwrapData<ProposalDetailResponse>(proposalQuery.data)

  if (proposalQuery.isLoading) return <LoadingState label="Cargando comparación de rondas…" />
  if (proposalQuery.error instanceof ApiError && proposalQuery.error.status === 404) {
    return <ErrorBanner message="Esta propuesta no está disponible." />
  }
  if (proposalQuery.error) {
    return <ErrorBanner message={normalizeApiError(proposalQuery.error).message} />
  }
  if (!proposal) return null

  if (proposal.snapshots.length < 2) {
    return (
      <div className="max-w-3xl">
        <EmptyState
          title="Esta propuesta no tiene rondas de negociación"
          description="Solo hay una versión enviada, no hay nada que comparar todavía."
        />
      </div>
    )
  }

  const round0 = proposal.snapshots[0]
  const round1 = proposal.snapshots[1]
  const requirements = [...round1.requirements].sort((a, b) => a.display_order - b.display_order)
  const round0Answers = new Map(round0.answers.map((a) => [a.requirement_id, a]))
  const round1Answers = new Map(round1.answers.map((a) => [a.requirement_id, a]))

  const costItemIds = Array.from(
    new Set([...round0.cost_items.map((c) => c.id), ...round1.cost_items.map((c) => c.id)]),
  )
  const round0CostItems = new Map(round0.cost_items.map((c) => [c.id, c]))
  const round1CostItems = new Map(round1.cost_items.map((c) => [c.id, c]))

  const renderAnswerCell = (answer: AnswerResponse | undefined, showStatus: boolean) => (
    <div className="flex flex-col gap-1">
      <span>{formatAnswerValue(answer?.value)}</span>
      {showStatus && answer && <StatusBadge label={translateAnswerStatus(answer.status)} />}
    </div>
  )

  const renderCostItemCell = (item: SnapshotCostItemResponse | undefined, showStatus: boolean) => {
    if (!item) return <span className="text-muted-foreground">—</span>
    return (
      <div className="flex flex-col gap-1">
        <span>
          {item.quantity} × {item.unit_price} {item.currency}
        </span>
        {showStatus && <StatusBadge label={translateCostItemStatus(item.status)} />}
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-lg font-semibold text-foreground">
        Comparación de rondas — {round1.vendor_org_name}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">{round1.evaluation_name}</p>
      {proposal.reopened_reason && (
        <p className="mt-2 text-sm text-muted-foreground">
          Motivo de la reapertura: {proposal.reopened_reason}
        </p>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">Respuestas</h2>
        <div className="mt-2 overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Requerimiento</TableHead>
                <TableHead>Ronda 0</TableHead>
                <TableHead>Ronda 1</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requirements.map((requirement) => (
                <TableRow key={requirement.id}>
                  <TableCell>{requirement.title}</TableCell>
                  <TableCell>
                    {renderAnswerCell(round0Answers.get(requirement.id), false)}
                  </TableCell>
                  <TableCell>{renderAnswerCell(round1Answers.get(requirement.id), true)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      {costItemIds.length > 0 && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Costos</h2>
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Concepto</TableHead>
                  <TableHead>Ronda 0</TableHead>
                  <TableHead>Ronda 1</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {costItemIds.map((id) => {
                  const item = round1CostItems.get(id) ?? round0CostItems.get(id)
                  return (
                    <TableRow key={id}>
                      <TableCell>{item?.concept}</TableCell>
                      <TableCell>{renderCostItemCell(round0CostItems.get(id), false)}</TableCell>
                      <TableCell>{renderCostItemCell(round1CostItems.get(id), true)}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </section>
      )}

      {(round0.tco_result || round1.tco_result) && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">TCO total</h2>
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ronda 0</TableHead>
                  <TableHead>Ronda 1</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>
                    {round0.tco_result
                      ? `${round0.tco_result.grand_total} ${round0.tco_result.base_currency}`
                      : 'No disponible'}
                  </TableCell>
                  <TableCell>
                    {round1.tco_result
                      ? `${round1.tco_result.grand_total} ${round1.tco_result.base_currency}`
                      : 'No disponible'}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </div>
  )
}
