import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet,
  useGetResultsApiV1EvaluationsEvaluationIdResultsGet,
  useUpsertScoreApiV1EvaluationsEvaluationIdProposalsProposalIdScoresRequirementIdPut,
  type EvaluationDetailResponse,
  type ProposalDetailResponse,
  type ResultsResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { PriorityBadge } from '@/components/PriorityBadge'
import { UpdatedByBadge } from '@/components/UpdatedByBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { normalizeApiError } from '@/lib/errors'
import { translateDimension } from '@/lib/enumLabels'
import { ScoreInput } from '@/features/scoring/components/ScoreInput'
import { BuyerDocumentsList } from '@/features/scoring/components/BuyerDocumentsList'

interface Draft {
  score: number | null
  comment: string
}

// Mirrors procurawise.shared.roles.SCORE_WRITE_ROLES - internal_collaborator
// and approver can view this page (BUYER_READ_ROLES) but the backend 403s
// their score writes (Fase 9 Block 3), so the inputs must never look
// editable to them in the first place.
const SCORE_WRITE_ROLES = [
  'evaluation_owner',
  'evaluator_functional',
  'evaluator_technical',
  'evaluator_economic',
]

export function ScoringPage() {
  const { evaluationId, proposalId } = useParams<{ evaluationId: string; proposalId: string }>()
  const { actor } = useAuth()
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const proposalQuery = useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet(
    evaluationId!,
    proposalId!,
  )
  const proposal = unwrapData<ProposalDetailResponse>(proposalQuery.data)

  const resultsQuery = useGetResultsApiV1EvaluationsEvaluationIdResultsGet(evaluationId!)
  const results = unwrapData<ResultsResponse>(resultsQuery.data)

  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [initialized, setInitialized] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [conflictIds, setConflictIds] = useState<Set<string>>(new Set())

  const proposalResult = results?.proposals.find((p) => p.proposal_id === proposalId)
  const scoresByRequirement = new Map(
    (proposalResult?.scores ?? []).map((s) => [s.requirement_id, s]),
  )
  const requirements = proposal?.snapshot?.requirements ?? []

  useEffect(() => {
    if (initialized || requirements.length === 0) return
    const next: Record<string, Draft> = {}
    for (const requirement of requirements) {
      const existing = scoresByRequirement.get(requirement.id)
      next[requirement.id] = {
        score: existing?.raw_score ?? null,
        comment: existing?.comment ?? '',
      }
    }
    setDrafts(next)
    setInitialized(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialized, requirements.length])

  const upsertScore =
    useUpsertScoreApiV1EvaluationsEvaluationIdProposalsProposalIdScoresRequirementIdPut()

  if (evaluationQuery.isLoading || proposalQuery.isLoading || resultsQuery.isLoading) {
    return <LoadingState label="Cargando calificación…" />
  }
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (proposalQuery.error instanceof ApiError && proposalQuery.error.status === 404) {
    return <ErrorBanner message="Esta propuesta no está disponible." />
  }
  if (evaluationQuery.error)
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  if (proposalQuery.error)
    return <ErrorBanner message={normalizeApiError(proposalQuery.error).message} />
  if (!evaluation || !proposal) return null

  if (proposal.status !== 'submitted' || !proposal.snapshot) {
    return <ErrorBanner message="Solo las propuestas enviadas pueden calificarse." />
  }

  const canWriteScores = Boolean(actor?.role && SCORE_WRITE_ROLES.includes(actor.role))
  const isEditable = evaluation.status === 'evaluating' && canWriteScores
  const scoredCount = requirements.filter((r) => scoresByRequirement.has(r.id)).length

  const handleSave = async (requirementId: string) => {
    const draft = drafts[requirementId]
    if (!draft || draft.score === null) return
    const existing = scoresByRequirement.get(requirementId)
    setSavingId(requirementId)
    try {
      await upsertScore.mutateAsync({
        evaluationId: evaluationId!,
        proposalId: proposalId!,
        requirementId,
        data: {
          score: draft.score,
          comment: draft.comment.trim() || undefined,
          version: existing?.version,
        },
      })
      await queryClient.invalidateQueries({
        queryKey: getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey(evaluationId),
      })
      setRowErrors((prev) => {
        const next = { ...prev }
        delete next[requirementId]
        return next
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflictIds((prev) => new Set(prev).add(requirementId))
      } else {
        setRowErrors((prev) => ({ ...prev, [requirementId]: normalizeApiError(error).message }))
      }
    } finally {
      setSavingId(null)
    }
  }

  const handleResolveConflict = async (requirementId: string) => {
    const queryKey = getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey(evaluationId)
    await queryClient.refetchQueries({ queryKey })
    const fresh = unwrapData<ResultsResponse>(queryClient.getQueryData(queryKey))
    const freshScore = fresh?.proposals
      .find((p) => p.proposal_id === proposalId)
      ?.scores.find((s) => s.requirement_id === requirementId)
    setDrafts((prev) => ({
      ...prev,
      [requirementId]: { score: freshScore?.raw_score ?? null, comment: freshScore?.comment ?? '' },
    }))
    setConflictIds((prev) => {
      const next = new Set(prev)
      next.delete(requirementId)
      return next
    })
  }

  const renderDimension = (dimension: 'functional' | 'technical') => {
    const dimensionRequirements = requirements
      .filter((r) => r.dimension === dimension)
      .sort((a, b) => a.display_order - b.display_order)
    if (dimensionRequirements.length === 0) return null

    return (
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">{translateDimension(dimension)}</h2>
        <div className="mt-2 flex flex-col gap-4">
          {dimensionRequirements.map((requirement) => {
            const draft = drafts[requirement.id] ?? { score: null, comment: '' }
            const existing = scoresByRequirement.get(requirement.id)
            const previewPoints =
              draft.score !== null
                ? Math.round((draft.score / 5) * requirement.weight * 100) / 100
                : null
            const hasConflict = conflictIds.has(requirement.id)

            return (
              <div key={requirement.id} className="rounded-md border border-border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">{requirement.title}</h3>
                  <PriorityBadge priority={requirement.priority} />
                  <span className="text-xs text-muted-foreground">Peso: {requirement.weight}</span>
                  {existing && (
                    <UpdatedByBadge
                      updatedByMembershipId={existing.evaluator_membership_id}
                      viewerMembershipId={actor?.membership_id}
                    />
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{requirement.description}</p>

                <div className="mt-3">
                  <ScoreInput
                    requirementId={requirement.id}
                    value={draft.score}
                    disabled={!isEditable}
                    onChange={(score) =>
                      setDrafts((prev) => ({ ...prev, [requirement.id]: { ...draft, score } }))
                    }
                  />
                </div>

                <div className="mt-2">
                  <Textarea
                    placeholder="Comentario (opcional)"
                    value={draft.comment}
                    disabled={!isEditable}
                    onChange={(event) =>
                      setDrafts((prev) => ({
                        ...prev,
                        [requirement.id]: { ...draft, comment: event.target.value },
                      }))
                    }
                  />
                </div>

                {previewPoints !== null && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Vista previa: {previewPoints} pts (el valor oficial lo confirma el servidor)
                  </p>
                )}

                {rowErrors[requirement.id] && (
                  <div className="mt-2">
                    <ErrorBanner message={rowErrors[requirement.id]} />
                  </div>
                )}

                {hasConflict && (
                  <div className="mt-2 flex items-center gap-2">
                    <ErrorBanner message="Los datos cambiaron desde que cargaste esta calificación." />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => handleResolveConflict(requirement.id)}
                    >
                      Recargar
                    </Button>
                  </div>
                )}

                {isEditable && !hasConflict && (
                  <Button
                    type="button"
                    size="sm"
                    className="mt-3"
                    disabled={draft.score === null || savingId === requirement.id}
                    onClick={() => handleSave(requirement.id)}
                  >
                    {savingId === requirement.id ? 'Guardando…' : 'Guardar calificación'}
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      </section>
    )
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">
          {proposal.snapshot.vendor_org_name}
        </h1>
        <StatusBadge label="Enviada" />
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{proposal.snapshot.evaluation_name}</p>

      <div className="mt-2 text-sm text-muted-foreground" role="status">
        Calificados: {scoredCount} / {requirements.length}
      </div>

      {!isEditable && evaluation.status !== 'evaluating' && (
        <p className="mt-2 text-sm text-muted-foreground">
          La evaluación ya no está en curso; las calificaciones son de solo lectura.
        </p>
      )}
      {!isEditable && evaluation.status === 'evaluating' && !canWriteScores && (
        <p className="mt-2 text-sm text-muted-foreground">
          Tu rol puede revisar esta calificación, pero no puede modificarla.
        </p>
      )}

      {renderDimension('functional')}
      {renderDimension('technical')}

      <BuyerDocumentsList evaluationId={evaluationId!} proposalId={proposalId!} />
    </div>
  )
}
