import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  type EvaluationDetailResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { normalizeApiError } from '@/lib/errors'
import { useAuth } from '@/auth/AuthContext'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
import { translateEvaluationStatus } from '@/lib/enumLabels'
import { WizardStepper } from './WizardStepper'
import { WizardStepMetadata } from './WizardStepMetadata'
import { WizardStepRequirements } from './WizardStepRequirements'
import { WizardStepVendors } from './WizardStepVendors'
import { WizardStepReview } from './WizardStepReview'
import { deriveWizardStep, type WizardStep } from './deriveWizardStep'

/** Guided evaluation-creation flow (Fase 10). Reachable at `/evaluations/new`
 * (no id yet) and `/evaluations/:evaluationId/wizard` (resume). The current
 * step is initialized once from `deriveWizardStep(evaluation)` - derived
 * from the evaluation's real server state, never a persisted `wizard_step`
 * field - and from then on is controlled explicitly by "Siguiente"/"Atrás"/
 * the stepper, so completing a step doesn't yank the user forward mid-edit.
 * A reload always re-runs the derivation, which is what satisfies "sin
 * pérdida de datos al recargar" without any autosave/version machinery. */
export function EvaluationWizard() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId ?? '', {
    query: { enabled: Boolean(evaluationId) },
  })
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  // Fase 26 (Hardening): "adjust state during render" instead of a
  // `useEffect` that calls `setState` synchronously in its body
  // (`react-hooks/set-state-in-effect`) - see EconomicWeightsForm.tsx for
  // the same pattern applied to a simpler (synchronously-available) case.
  // This one also has to wait for `evaluationQuery` to resolve
  // asynchronously (`evaluation` starts `undefined`), which still works
  // here: React just re-renders this component again once the query
  // updates, and *that* render is where the adjustment below fires -
  // synchronously, without waiting on a separate effect+re-render round
  // trip the way the original version did.
  const [wizardState, setWizardState] = useState<{
    hasInitialized: boolean
    initializedFor: string | null
    step: WizardStep
  }>(() => ({ hasInitialized: false, initializedFor: null, step: 1 }))

  const currentEvaluationId = evaluationId ?? null
  const stillLoadingForInit = Boolean(evaluationId) && evaluation === undefined
  if (
    !stillLoadingForInit &&
    (!wizardState.hasInitialized || wizardState.initializedFor !== currentEvaluationId)
  ) {
    setWizardState({
      hasInitialized: true,
      initializedFor: currentEvaluationId,
      step: deriveWizardStep(evaluation),
    })
  }
  const step = wizardState.step
  const setStep = (next: WizardStep) => setWizardState((prev) => ({ ...prev, step: next }))

  if (!isOwner) {
    return <Navigate to={evaluationId ? `/evaluations/${evaluationId}` : '/evaluations'} replace />
  }

  if (evaluationId && evaluationQuery.isLoading) {
    return <LoadingState label="Cargando evaluación…" />
  }
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (evaluation && evaluation.status !== 'draft') {
    return <Navigate to={`/evaluations/${evaluation.id}`} replace />
  }

  const derivedStep = deriveWizardStep(evaluation)
  const maxReachableStep = evaluation ? derivedStep : 1

  const invalidateEvaluation = () => {
    if (!evaluationId) return
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
    })
  }

  const handleCreated = (created: EvaluationDetailResponse) => {
    setWizardState({ hasInitialized: true, initializedFor: created.id, step: 2 })
    navigate(`/evaluations/${created.id}/wizard`, { replace: true })
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">
          {evaluation ? evaluation.name : 'Nueva evaluación'}
        </h1>
        {evaluation && <StatusBadge label={translateEvaluationStatus(evaluation.status)} />}
      </div>
      <WizardStepper
        currentStep={step}
        maxReachableStep={maxReachableStep}
        onStepSelect={setStep}
      />

      <div className="mt-6">
        {step === 1 && (
          <WizardStepMetadata
            evaluation={evaluation}
            onCreated={handleCreated}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && evaluation && (
          <WizardStepRequirements
            evaluation={evaluation}
            onChanged={invalidateEvaluation}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && evaluation && (
          <WizardStepVendors
            evaluation={evaluation}
            onChanged={invalidateEvaluation}
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
          />
        )}
        {step === 4 && evaluation && (
          <WizardStepReview
            evaluation={evaluation}
            onBack={() => setStep(3)}
            onStarted={() => navigate(`/evaluations/${evaluation.id}`, { replace: true })}
          />
        )}
      </div>
    </div>
  )
}
