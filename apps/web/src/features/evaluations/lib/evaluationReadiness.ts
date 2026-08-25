import type { EvaluationDetailResponse } from '@/api/client'

type Dimension = 'functional' | 'technical'

export const DIMENSION_WEIGHT_TARGETS: Record<Dimension, number> = {
  functional: 40,
  technical: 20,
}
const WEIGHT_TOLERANCE = 1e-6

// UAT-02 (R4): requirement weights are still authored/stored/validated as
// raw points against DIMENSION_WEIGHT_TARGETS (evaluations/models.py's
// DIMENSION_MAX_POINTS, unchanged, no migration) - these two helpers are
// presentation-only conversions to/from the percentage a human actually
// thinks in ("this is 25% of the functional budget"), matching how
// EconomicWeightsForm.tsx already frames its own weights as 0-100%.
export function pointsToPercent(points: number, dimension: Dimension): number {
  return (points / DIMENSION_WEIGHT_TARGETS[dimension]) * 100
}

export function percentToPoints(percent: number, dimension: Dimension): number {
  return (percent / 100) * DIMENSION_WEIGHT_TARGETS[dimension]
}

function formatPercent(points: number, dimension: Dimension): string {
  return String(Math.round(pointsToPercent(points, dimension) * 10) / 10)
}

export function weightOf(evaluation: EvaluationDetailResponse, dimension: Dimension): number {
  return evaluation.requirements
    .filter((r) => r.dimension === dimension)
    .reduce((sum, r) => sum + r.weight, 0)
}

export function hasCompleteWeights(evaluation: EvaluationDetailResponse): boolean {
  return (Object.keys(DIMENSION_WEIGHT_TARGETS) as Dimension[]).every(
    (dimension) =>
      Math.abs(weightOf(evaluation, dimension) - DIMENSION_WEIGHT_TARGETS[dimension]) <=
      WEIGHT_TOLERANCE,
  )
}

export function hasLinkedVendor(evaluation: EvaluationDetailResponse): boolean {
  return evaluation.linked_vendor_count > 0
}

export function hasApprover(evaluation: EvaluationDetailResponse): boolean {
  return evaluation.approver_membership_id !== null
}

export function hasResponseDeadline(evaluation: EvaluationDetailResponse): boolean {
  return evaluation.response_deadline !== null
}

/** ADR 0026 (R2) - a Reviewer is optional per evaluation; `hasReviewer`
 * mirrors `hasApprover` for the new stage. */
export function hasReviewer(evaluation: EvaluationDetailResponse): boolean {
  return evaluation.reviewer_membership_id !== null
}

/** Shared by every *PreconditionReasons function below (previously
 * duplicated three times verbatim) - the tolerance check stays in points
 * (exactly matching evaluations/service.py's _WEIGHT_TOLERANCE), only the
 * displayed numbers convert to percent (UAT-02). */
function weightReasons(evaluation: EvaluationDetailResponse): string[] {
  const reasons: string[] = []
  const functionalWeight = weightOf(evaluation, 'functional')
  const technicalWeight = weightOf(evaluation, 'technical')

  if (Math.abs(functionalWeight - DIMENSION_WEIGHT_TARGETS.functional) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos funcionales deben sumar 100% (llevan ${formatPercent(functionalWeight, 'functional')}%).`,
    )
  }
  if (Math.abs(technicalWeight - DIMENSION_WEIGHT_TARGETS.technical) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos técnicos deben sumar 100% (llevan ${formatPercent(technicalWeight, 'technical')}%).`,
    )
  }
  return reasons
}

/** Client-side preview of the same preconditions `start-collection` enforces
 * server-side (evaluations/service.py::start_collection) - never the source
 * of truth, only a UX hint (brief §23/CLAUDE.md §5). Shared between
 * `VendorsPage` and the Fase 10 wizard so the 40/20 threshold isn't
 * duplicated a third time. */
export function startCollectionPreconditionReasons(evaluation: EvaluationDetailResponse): string[] {
  const reasons = weightReasons(evaluation)
  if (!hasLinkedVendor(evaluation)) {
    reasons.push('Debes vincular al menos un proveedor.')
  }
  if (evaluation.approval_status !== 'approved') {
    reasons.push('La evaluación debe estar aprobada antes de publicarse.')
  }
  return reasons
}

export function isReadyToStartCollection(evaluation: EvaluationDetailResponse): boolean {
  return startCollectionPreconditionReasons(evaluation).length === 0
}

/** Fase 12 (plan §16 "approval readiness") = draft readiness (weights +
 * vendor) + approver assigned + response_deadline set. Same client-preview
 * caveat as startCollectionPreconditionReasons above - the backend's
 * GET .../publication-readiness is the source of truth. */
export function requestApprovalPreconditionReasons(evaluation: EvaluationDetailResponse): string[] {
  const reasons = weightReasons(evaluation)
  if (!hasLinkedVendor(evaluation)) {
    reasons.push('Debes vincular al menos un proveedor.')
  }
  if (!hasApprover(evaluation)) {
    reasons.push('Debes asignar un aprobador.')
  }
  if (!hasResponseDeadline(evaluation)) {
    reasons.push('Debes establecer una fecha límite de respuesta.')
  }
  // ADR 0026 (R2): only applies when a reviewer is actually assigned - an
  // evaluation that never uses the (optional) review stage is unaffected.
  if (hasReviewer(evaluation) && evaluation.review_status !== 'approved') {
    reasons.push('La evaluación debe pasar revisión antes de poder pedir aprobación.')
  }
  return reasons
}

export function isReadyToRequestApproval(evaluation: EvaluationDetailResponse): boolean {
  return requestApprovalPreconditionReasons(evaluation).length === 0
}

/** ADR 0026 (R2) - mirrors requestApprovalPreconditionReasons for the
 * optional review stage: draft readiness (weights + vendor) + a reviewer
 * assigned. No response_deadline requirement - that's an approval-stage
 * precondition, unaffected by whether the evaluation is reviewed first. */
export function requestReviewPreconditionReasons(evaluation: EvaluationDetailResponse): string[] {
  const reasons = weightReasons(evaluation)
  if (!hasLinkedVendor(evaluation)) {
    reasons.push('Debes vincular al menos un proveedor.')
  }
  if (!hasReviewer(evaluation)) {
    reasons.push('Debes asignar un revisor.')
  }
  return reasons
}

export function isReadyToRequestReview(evaluation: EvaluationDetailResponse): boolean {
  return requestReviewPreconditionReasons(evaluation).length === 0
}
