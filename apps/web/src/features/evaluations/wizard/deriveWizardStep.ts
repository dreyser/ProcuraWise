import type { EvaluationDetailResponse } from '@/api/client'
import { hasCompleteWeights, hasLinkedVendor } from '@/features/evaluations/lib/evaluationReadiness'

export type WizardStep = 1 | 2 | 3 | 4

/** Derives the wizard's resumable step purely from the Evaluation's real
 * server state (`requirements`, `linked_vendor_count`) - never from a
 * persisted `wizard_step` field or client-only memory. This is the Fase 10
 * founder decision: "no pérdida de datos al recargar" is satisfied because
 * every confirmed step already persisted via its own endpoint, so a reload
 * can always re-derive where the user left off instead of tracking it
 * separately (no `version`/concurrency machinery needed, unlike
 * ProposalAnswer's autosave). */
export function deriveWizardStep(evaluation: EvaluationDetailResponse | undefined): WizardStep {
  if (!evaluation) return 1
  if (!hasCompleteWeights(evaluation)) return 2
  if (!hasLinkedVendor(evaluation)) return 3
  return 4
}
