import { useParams } from 'react-router-dom'
import {
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet,
  type EvaluationDetailResponse,
  type ProposalDetailResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { normalizeApiError } from '@/lib/errors'
import { EconomicAssessmentPanel } from '@/features/scoring/components/EconomicAssessmentPanel'
import { TcoResultPage } from '@/features/tco/pages/TcoResultPage'

// Mirrors procurawise.shared.roles.SCORE_WRITE_ROLES (same list ScoringPage.tsx
// uses) - internal_collaborator/approver can view (BUYER_READ_ROLES) but the
// backend 403s their economic-assessment writes.
const SCORE_WRITE_ROLES = [
  'evaluation_owner',
  'evaluator_functional',
  'evaluator_technical',
  'evaluator_economic',
]

/** UAT-17 (R4): "Evaluación Comercial" - TCO (read-only) and the commercial/
 * risk EconomicAssessmentPanel used to live on two disconnected pages (a
 * standalone /tco route reached only via "Ver TCO", and a section buried at
 * the bottom of ScoringPage.tsx) even though both describe the same 40-point
 * economic dimension of one proposal. Neither TCO's nor EconomicAssessment's
 * own data model changed - this only relocates where the buyer looks at
 * them. Reached from the Propuestas table's row actions (replacing "Ver
 * TCO"), not a new EvaluationTabNav tab: both pieces are proposal-scoped,
 * not evaluation-scoped, same reasoning ScoringPage.tsx already follows. */
export function CommercialEvaluationPage() {
  const { evaluationId, proposalId } = useParams<{ evaluationId: string; proposalId: string }>()
  const { actor } = useAuth()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const proposalQuery = useGetProposalApiV1EvaluationsEvaluationIdProposalsProposalIdGet(
    evaluationId!,
    proposalId!,
  )
  const proposal = unwrapData<ProposalDetailResponse>(proposalQuery.data)
  const currentSnapshot = proposal?.snapshots.at(-1)

  if (evaluationQuery.isLoading || proposalQuery.isLoading) {
    return <LoadingState label="Cargando evaluación comercial…" />
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

  if (proposal.status !== 'submitted' || !currentSnapshot) {
    return <ErrorBanner message="Solo las propuestas enviadas tienen evaluación comercial." />
  }

  const canWriteScores = Boolean(actor?.role && SCORE_WRITE_ROLES.includes(actor.role))
  const isEditable = evaluation.status === 'evaluating' && canWriteScores
  // UAT-14 (R1B, Decisión F) - unchanged rule, just relocated with the panel
  // itself: functional/technical evaluators never see commercial/risk data,
  // outside their assigned responsibility.
  const canSeeEconomic =
    actor?.role !== 'evaluator_functional' && actor?.role !== 'evaluator_technical'

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{currentSnapshot.vendor_org_name}</h1>
        <StatusBadge label="Enviada" />
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{currentSnapshot.evaluation_name}</p>
      <p className="mt-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Evaluación comercial
      </p>

      <div className="mt-6">
        <TcoResultPage />
      </div>

      {canSeeEconomic && (
        <div className="mt-6">
          <EconomicAssessmentPanel
            evaluationId={evaluationId!}
            proposalId={proposalId!}
            isEditable={isEditable}
          />
        </div>
      )}
    </div>
  )
}
