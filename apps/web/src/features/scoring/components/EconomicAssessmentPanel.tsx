import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentGetQueryKey,
  getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey,
  useGetEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentGet,
  useUpsertEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentPut,
  type CriterionScoreRequest,
  type EconomicAssessmentResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { normalizeApiError } from '@/lib/errors'
import { economicCriterionGuidanceFor, translateEconomicCriterion } from '@/lib/enumLabels'

const COMMERCIAL_KEYS = [
  'payment_terms',
  'price_protection',
  'contractual_flexibility',
  'discounts_incentives',
  'billing_transparency',
] as const

const RISK_KEYS = [
  'variable_cost_exposure',
  'increases_indexation',
  'assumptions_exclusions',
  'fx_fiscal_regulatory',
  'exit_portability_lockin',
] as const

// Mirrors scoring.service._EXTREME_SCORES exactly - extreme scores and "N/A"
// both require a comment server-side; the client enforces the same rule so
// a save attempt fails locally with a clear message instead of a 422 round
// trip.
const EXTREME_SCORES = new Set([0, 1, 2, 5])

interface CriterionDraft {
  score: number | null
  isNA: boolean
  comment: string
}

function emptyDraft(): CriterionDraft {
  return { score: null, isNA: false, comment: '' }
}

function draftsFromAssessment(
  assessment: EconomicAssessmentResponse | undefined,
): Record<string, CriterionDraft> {
  const byKey = new Map(
    [...(assessment?.commercial_scores ?? []), ...(assessment?.risk_scores ?? [])].map((s) => [
      s.criterion_key,
      s,
    ]),
  )
  const next: Record<string, CriterionDraft> = {}
  for (const key of [...COMMERCIAL_KEYS, ...RISK_KEYS]) {
    const existing = byKey.get(key)
    next[key] = existing
      ? { score: existing.score, isNA: existing.score === null, comment: existing.comment ?? '' }
      : emptyDraft()
  }
  return next
}

interface CriterionRowProps {
  criterionKey: string
  draft: CriterionDraft
  disabled: boolean
  onChange: (draft: CriterionDraft) => void
}

function CriterionRow({ criterionKey, draft, disabled, onChange }: CriterionRowProps) {
  const commentRequired = draft.isNA || (draft.score !== null && EXTREME_SCORES.has(draft.score))
  const groupId = `economic-criterion-${criterionKey}`
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-sm font-medium text-foreground">
        {translateEconomicCriterion(criterionKey)}
      </p>
      {economicCriterionGuidanceFor(criterionKey) && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {economicCriterionGuidanceFor(criterionKey)}
        </p>
      )}
      <fieldset aria-label={`Calificación de ${translateEconomicCriterion(criterionKey)}`}>
        <div id={groupId} className="mt-2 flex flex-wrap gap-1.5">
          {[0, 1, 2, 3, 4, 5].map((option) => (
            <label
              key={option}
              className={`flex size-9 cursor-pointer items-center justify-center rounded-md border text-sm ${
                !draft.isNA && draft.score === option
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border text-foreground hover:bg-muted'
              } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
            >
              <input
                type="radio"
                name={groupId}
                value={option}
                checked={!draft.isNA && draft.score === option}
                disabled={disabled}
                onChange={() => onChange({ ...draft, score: option, isNA: false })}
                aria-label={`${translateEconomicCriterion(criterionKey)}: ${option}`}
                className="sr-only"
              />
              {option}
            </label>
          ))}
          <label
            className={`flex h-9 cursor-pointer items-center justify-center rounded-md border px-2 text-sm ${
              draft.isNA
                ? 'border-foreground bg-foreground text-background'
                : 'border-border text-foreground hover:bg-muted'
            } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
          >
            <input
              type="radio"
              name={groupId}
              value="na"
              checked={draft.isNA}
              disabled={disabled}
              onChange={() => onChange({ ...draft, score: null, isNA: true })}
              aria-label={`${translateEconomicCriterion(criterionKey)}: N/A`}
              className="sr-only"
            />
            N/A
          </label>
        </div>
      </fieldset>
      <div className="mt-2">
        <Textarea
          aria-label={`Comentario: ${translateEconomicCriterion(criterionKey)}`}
          placeholder={
            commentRequired
              ? `Comentario para "${translateEconomicCriterion(criterionKey)}" (obligatorio)`
              : `Comentario para "${translateEconomicCriterion(criterionKey)}" (opcional)`
          }
          value={draft.comment}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, comment: event.target.value })}
        />
      </div>
    </div>
  )
}

interface EconomicAssessmentPanelProps {
  evaluationId: string
  proposalId: string
  isEditable: boolean
}

/** Fase 20 (ADR 0009) - captures the 10 fixed commercial/risk sub-criteria
 * as one unit (mirrors the backend's full-replace PUT semantics - there is
 * no per-criterion save). The TCO-normalized 70% component is never
 * captured here - it's computed automatically from Fase 19's frozen
 * tco_result and only shown as a read value on ResultsPage. */
export function EconomicAssessmentPanel({
  evaluationId,
  proposalId,
  isEditable,
}: EconomicAssessmentPanelProps) {
  const queryClient = useQueryClient()
  const assessmentQuery =
    useGetEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentGet(
      evaluationId,
      proposalId,
    )
  const notFound = assessmentQuery.error instanceof ApiError && assessmentQuery.error.status === 404
  const assessment = unwrapData<EconomicAssessmentResponse>(assessmentQuery.data)

  // Fase 26 (Hardening): "adjust state during render" instead of a
  // `useEffect` that calls `setState` synchronously in its body
  // (`react-hooks/set-state-in-effect`) - same shape as
  // EvaluationWizard.tsx's "initialize once the async query resolves"
  // fix. `drafts`/`initialized` live in one state object so the seed-from-
  // server-data adjustment below sets both atomically.
  const [assessmentState, setAssessmentState] = useState<{
    initialized: boolean
    drafts: Record<string, CriterionDraft>
  }>({ initialized: false, drafts: {} })

  if (!assessmentState.initialized && !assessmentQuery.isLoading && (assessment || notFound)) {
    setAssessmentState({ initialized: true, drafts: draftsFromAssessment(assessment) })
  }
  const drafts = assessmentState.drafts
  const setDrafts = (
    updater: (prev: Record<string, CriterionDraft>) => Record<string, CriterionDraft>,
  ) => setAssessmentState((prev) => ({ ...prev, drafts: updater(prev.drafts) }))
  const [validationError, setValidationError] = useState<string | null>(null)

  const upsert =
    useUpsertEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentPut(
      {
        mutation: {
          onSuccess: (response) => {
            queryClient.setQueryData(
              getGetEconomicAssessmentApiV1EvaluationsEvaluationIdProposalsProposalIdEconomicAssessmentGetQueryKey(
                evaluationId,
                proposalId,
              ),
              response,
            )
            queryClient.invalidateQueries({
              queryKey: getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey(evaluationId),
            })
          },
        },
      },
    )

  if (assessmentQuery.isLoading) {
    return <p className="mt-6 text-sm text-muted-foreground">Cargando evaluación económica…</p>
  }
  if (assessmentQuery.error && !notFound) {
    return <ErrorBanner message={normalizeApiError(assessmentQuery.error).message} />
  }

  const toRequest = (keys: readonly string[]): CriterionScoreRequest[] =>
    keys.map((key) => {
      const draft = drafts[key] ?? emptyDraft()
      return {
        criterion_key: key,
        score: draft.isNA ? null : draft.score,
        comment: draft.comment.trim() || null,
      }
    })

  const handleSave = async () => {
    setValidationError(null)
    for (const key of [...COMMERCIAL_KEYS, ...RISK_KEYS]) {
      const draft = drafts[key] ?? emptyDraft()
      if (!draft.isNA && draft.score === null) {
        setValidationError('Completa los 10 criterios (o márcalos como N/A) antes de guardar.')
        return
      }
      const commentRequired =
        draft.isNA || (draft.score !== null && EXTREME_SCORES.has(draft.score))
      if (commentRequired && !draft.comment.trim()) {
        setValidationError(
          `Falta comentario obligatorio en "${translateEconomicCriterion(key)}" (calificación extrema o N/A).`,
        )
        return
      }
    }
    try {
      await upsert.mutateAsync({
        evaluationId,
        proposalId,
        data: {
          commercial_scores: toRequest(COMMERCIAL_KEYS),
          risk_scores: toRequest(RISK_KEYS),
          version: assessment?.version,
        },
      })
    } catch {
      // surfaced below via upsert.isError
    }
  }

  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold text-foreground">Condiciones comerciales y riesgo</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        El componente de TCO normalizado (70% del puntaje económico) se calcula automáticamente y se
        muestra en Resultados - aquí solo se califican las condiciones comerciales y el riesgo.
      </p>

      <div className="mt-3">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">
          Condiciones comerciales
        </h3>
        <div className="mt-2 flex flex-col gap-3">
          {COMMERCIAL_KEYS.map((key) => (
            <CriterionRow
              key={key}
              criterionKey={key}
              draft={drafts[key] ?? emptyDraft()}
              disabled={!isEditable}
              onChange={(draft) => setDrafts((prev) => ({ ...prev, [key]: draft }))}
            />
          ))}
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">
          Riesgo y predictibilidad
        </h3>
        <div className="mt-2 flex flex-col gap-3">
          {RISK_KEYS.map((key) => (
            <CriterionRow
              key={key}
              criterionKey={key}
              draft={drafts[key] ?? emptyDraft()}
              disabled={!isEditable}
              onChange={(draft) => setDrafts((prev) => ({ ...prev, [key]: draft }))}
            />
          ))}
        </div>
      </div>

      {validationError && (
        <div className="mt-3">
          <ErrorBanner message={validationError} />
        </div>
      )}
      {upsert.isError && (
        <div className="mt-3">
          <ErrorBanner message={normalizeApiError(upsert.error).message} />
        </div>
      )}

      {isEditable && (
        <Button type="button" className="mt-3" disabled={upsert.isPending} onClick={handleSave}>
          {upsert.isPending ? 'Guardando…' : 'Guardar evaluación económica'}
        </Button>
      )}
    </section>
  )
}
