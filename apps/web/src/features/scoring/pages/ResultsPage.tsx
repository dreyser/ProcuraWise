import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useCompleteEvaluationApiV1EvaluationsEvaluationIdCompletePost,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetResultsApiV1EvaluationsEvaluationIdResultsGet,
  type EvaluationDetailResponse,
  type ResultsResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useActor } from '@/actor/ActorContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateEvaluationStatus, translateScoringStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'

export function ResultsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useActor()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const resultsQuery = useGetResultsApiV1EvaluationsEvaluationIdResultsGet(evaluationId!)
  const results = unwrapData<ResultsResponse>(resultsQuery.data)

  const [confirmComplete, setConfirmComplete] = useState(false)

  const completeEvaluation = useCompleteEvaluationApiV1EvaluationsEvaluationIdCompletePost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
        })
        setConfirmComplete(false)
      },
    },
  })

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando resultados…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  if (evaluation.status === 'draft' || evaluation.status === 'collecting_responses') {
    return (
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
          <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
        </div>
        <EvaluationTabNav evaluationId={evaluation.id} />
        <p className="mt-6 text-sm text-muted-foreground">
          Los resultados estarán disponibles cuando la evaluación pase a "En evaluación".
        </p>
      </div>
    )
  }

  const totalRequirements = evaluation.requirements.length
  const pendingByProposal = (results?.proposals ?? [])
    .filter((p) => p.scores.length < totalRequirements)
    .map(
      (p) =>
        `${p.vendor_org_name}: ${totalRequirements - p.scores.length} requerimiento(s) sin calificar`,
    )

  const canComplete =
    isOwner && evaluation.status === 'evaluating' && results?.scoring_status === 'complete'

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {resultsQuery.isLoading && <LoadingState label="Cargando resultados…" />}
      {resultsQuery.error && (
        <ErrorBanner message={normalizeApiError(resultsQuery.error).message} />
      )}

      {results && (
        <>
          <p className="mt-4 text-sm text-muted-foreground">{results.disclaimer}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Estado de calificación: {translateScoringStatus(results.scoring_status)}
          </p>

          {results.proposals.length === 0 && (
            <div className="mt-4">
              <EmptyState title="Todavía no hay propuestas enviadas con resultados" />
            </div>
          )}

          {results.proposals.length > 0 && (
            <div className="mt-4 overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Proveedor</TableHead>
                    <TableHead>Funcional</TableHead>
                    <TableHead>Técnico</TableHead>
                    <TableHead>Económico</TableHead>
                    <TableHead>Parcial</TableHead>
                    <TableHead>Alertas obligatorias</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {results.proposals.map((proposal) => (
                    <TableRow key={proposal.proposal_id}>
                      <TableCell>{proposal.vendor_org_name}</TableCell>
                      <TableCell>
                        {proposal.functional.earned_points} / {proposal.functional.maximum_points}
                      </TableCell>
                      <TableCell>
                        {proposal.technical.earned_points} / {proposal.technical.maximum_points}
                      </TableCell>
                      <TableCell>No disponible</TableCell>
                      <TableCell>
                        {proposal.partial_result.earned_points} /{' '}
                        {proposal.partial_result.maximum_points}
                      </TableCell>
                      <TableCell>
                        {proposal.mandatory_alerts_count > 0 ? (
                          <span className="text-amber-700">{proposal.mandatory_alerts_count}</span>
                        ) : (
                          0
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="px-4 py-2 text-xs text-muted-foreground">
                Orden estable por proveedor - no es un ranking ni implica adjudicación.
              </p>
            </div>
          )}

          {results.draft_proposals.length > 0 && (
            <div className="mt-4">
              <h2 className="text-sm font-semibold text-foreground">
                Propuestas aún no enviadas (sin resultados)
              </h2>
              <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
                {results.draft_proposals.map((draft) => (
                  <li key={draft.proposal_id}>{draft.vendor_org_name}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {isOwner && evaluation.status === 'evaluating' && (
        <section className="mt-8">
          <Button type="button" disabled={!canComplete} onClick={() => setConfirmComplete(true)}>
            Completar evaluación
          </Button>
          <DisabledActionHint reasons={canComplete ? [] : pendingByProposal} />
        </section>
      )}

      <ConfirmDialog
        open={confirmComplete}
        onOpenChange={setConfirmComplete}
        title="Completar evaluación"
        description="La evaluación quedará cerrada y todo pasará a solo lectura. No se declara ganador ni se presenta un ranking final."
        confirmLabel="Completar evaluación"
        isPending={completeEvaluation.isPending}
        onConfirm={() => completeEvaluation.mutate({ evaluationId: evaluation.id })}
      />
      {completeEvaluation.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(completeEvaluation.error).message} />
        </div>
      )}
    </div>
  )
}
