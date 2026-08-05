import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useListProposalsApiV1EvaluationsEvaluationIdProposalsGet,
  useListVendorOrganizationsApiV1VendorOrganizationsGet,
  useReopenProposalApiV1EvaluationsEvaluationIdProposalsProposalIdReopenPost,
  useStartEvaluationApiV1EvaluationsEvaluationIdStartEvaluationPost,
  type EvaluationDetailResponse,
  type ProposalSummaryResponse,
  type VendorOrganizationListResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateEvaluationStatus, translateProposalStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import { ReopenProposalDialog } from '@/features/proposals/components/ReopenProposalDialog'

const MAX_PROPOSAL_ROUNDS = 2

export function ProposalsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const proposalsQuery = useListProposalsApiV1EvaluationsEvaluationIdProposalsGet(evaluationId!)
  const proposals = unwrapData<ProposalSummaryResponse[]>(proposalsQuery.data) ?? []

  const namesQuery = useListVendorOrganizationsApiV1VendorOrganizationsGet({ limit: 100 })
  const namesCatalog = unwrapData<VendorOrganizationListResponse>(namesQuery.data)
  const nameById = new Map((namesCatalog?.items ?? []).map((item) => [item.id, item.name]))

  const [confirmStart, setConfirmStart] = useState(false)
  const [reopenTarget, setReopenTarget] = useState<ProposalSummaryResponse | null>(null)

  const startEvaluation = useStartEvaluationApiV1EvaluationsEvaluationIdStartEvaluationPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
        })
        setConfirmStart(false)
      },
    },
  })

  const reopenProposal = useReopenProposalApiV1EvaluationsEvaluationIdProposalsProposalIdReopenPost(
    {
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
          })
          queryClient.invalidateQueries({
            queryKey:
              getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey(evaluationId),
          })
          setReopenTarget(null)
        },
      },
    },
  )

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando propuestas…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  const submittedCount = proposals.filter((p) => p.status === 'submitted').length
  const canStartEvaluation =
    isOwner && evaluation.status === 'collecting_responses' && submittedCount > 0

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      <div className="mt-6">
        {proposalsQuery.isLoading && <LoadingState label="Cargando propuestas…" />}
        {proposalsQuery.error && (
          <ErrorBanner message={normalizeApiError(proposalsQuery.error).message} />
        )}
        {proposals.length === 0 && !proposalsQuery.isLoading && (
          <EmptyState title="Todavía no hay propuestas vinculadas" />
        )}
        {proposals.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Ronda</TableHead>
                  <TableHead>Última actualización</TableHead>
                  {evaluation.status === 'evaluating' || evaluation.status === 'completed' ? (
                    <TableHead>Acciones</TableHead>
                  ) : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((proposal) => {
                  const canReopen =
                    isOwner &&
                    evaluation.status === 'evaluating' &&
                    proposal.status === 'submitted' &&
                    proposal.round < MAX_PROPOSAL_ROUNDS - 1
                  return (
                    <TableRow key={proposal.id}>
                      <TableCell>{nameById.get(proposal.vendor_org_id) ?? 'Proveedor'}</TableCell>
                      <TableCell>
                        <StatusBadge label={translateProposalStatus(proposal.status)} />
                      </TableCell>
                      <TableCell>Ronda {proposal.round}</TableCell>
                      <TableCell>
                        {new Date(proposal.updated_at).toLocaleDateString('es-MX')}
                      </TableCell>
                      {evaluation.status === 'evaluating' || evaluation.status === 'completed' ? (
                        <TableCell>
                          {proposal.status === 'submitted' ? (
                            <div className="flex flex-col items-start gap-1">
                              <Link
                                to={`/evaluations/${evaluation.id}/proposals/${proposal.id}/score`}
                                className="text-sm text-foreground underline-offset-2 hover:underline"
                              >
                                Calificar
                              </Link>
                              <Link
                                to={`/evaluations/${evaluation.id}/proposals/${proposal.id}/tco`}
                                className="text-sm text-foreground underline-offset-2 hover:underline"
                              >
                                Ver TCO
                              </Link>
                              {proposal.round > 0 && (
                                <Link
                                  to={`/evaluations/${evaluation.id}/proposals/${proposal.id}/versions`}
                                  className="text-sm text-foreground underline-offset-2 hover:underline"
                                >
                                  Comparar rondas
                                </Link>
                              )}
                              {canReopen && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="mt-1"
                                  onClick={() => setReopenTarget(proposal)}
                                >
                                  Reabrir para negociación
                                </Button>
                              )}
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">
                              No enviada, sin calificar
                            </span>
                          )}
                        </TableCell>
                      ) : null}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {isOwner && evaluation.status === 'collecting_responses' && (
        <section className="mt-8">
          <Button
            type="button"
            disabled={!canStartEvaluation}
            onClick={() => setConfirmStart(true)}
          >
            Iniciar evaluación
          </Button>
          {submittedCount === 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              Ningún proveedor ha enviado su propuesta todavía.
            </p>
          )}
        </section>
      )}

      <ConfirmDialog
        open={confirmStart}
        onOpenChange={setConfirmStart}
        title="Iniciar evaluación"
        description="Las propuestas que sigan en borrador ya no podrán enviarse una vez que inicie la evaluación."
        confirmLabel="Iniciar evaluación"
        isPending={startEvaluation.isPending}
        onConfirm={() => startEvaluation.mutate({ evaluationId: evaluation.id })}
      />
      {startEvaluation.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(startEvaluation.error).message} />
        </div>
      )}

      {reopenTarget && (
        <ReopenProposalDialog
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setReopenTarget(null)
          }}
          vendorName={nameById.get(reopenTarget.vendor_org_id) ?? 'Proveedor'}
          isPending={reopenProposal.isPending}
          onConfirm={(data) =>
            reopenProposal.mutate({
              evaluationId: evaluation.id,
              proposalId: reopenTarget.id,
              data,
            })
          }
        />
      )}
      {reopenProposal.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(reopenProposal.error).message} />
        </div>
      )}
    </div>
  )
}
