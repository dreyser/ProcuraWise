import type { EvaluationDetailResponse } from '@/api/client'

type Dimension = 'functional' | 'technical'

export const DIMENSION_WEIGHT_TARGETS: Record<Dimension, number> = {
  functional: 40,
  technical: 20,
}
const WEIGHT_TOLERANCE = 1e-6

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

/** Client-side preview of the same preconditions `start-collection` enforces
 * server-side (evaluations/service.py::start_collection) - never the source
 * of truth, only a UX hint (brief §23/CLAUDE.md §5). Shared between
 * `VendorsPage` and the Fase 10 wizard so the 40/20 threshold isn't
 * duplicated a third time. */
export function startCollectionPreconditionReasons(evaluation: EvaluationDetailResponse): string[] {
  const reasons: string[] = []
  const functionalWeight = weightOf(evaluation, 'functional')
  const technicalWeight = weightOf(evaluation, 'technical')

  if (Math.abs(functionalWeight - DIMENSION_WEIGHT_TARGETS.functional) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos funcionales deben sumar ${DIMENSION_WEIGHT_TARGETS.functional} puntos (llevan ${functionalWeight}).`,
    )
  }
  if (Math.abs(technicalWeight - DIMENSION_WEIGHT_TARGETS.technical) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos técnicos deben sumar ${DIMENSION_WEIGHT_TARGETS.technical} puntos (llevan ${technicalWeight}).`,
    )
  }
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
  const reasons: string[] = []
  const functionalWeight = weightOf(evaluation, 'functional')
  const technicalWeight = weightOf(evaluation, 'technical')

  if (Math.abs(functionalWeight - DIMENSION_WEIGHT_TARGETS.functional) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos funcionales deben sumar ${DIMENSION_WEIGHT_TARGETS.functional} puntos (llevan ${functionalWeight}).`,
    )
  }
  if (Math.abs(technicalWeight - DIMENSION_WEIGHT_TARGETS.technical) > WEIGHT_TOLERANCE) {
    reasons.push(
      `Los requerimientos técnicos deben sumar ${DIMENSION_WEIGHT_TARGETS.technical} puntos (llevan ${technicalWeight}).`,
    )
  }
  if (!hasLinkedVendor(evaluation)) {
    reasons.push('Debes vincular al menos un proveedor.')
  }
  if (!hasApprover(evaluation)) {
    reasons.push('Debes asignar un aprobador.')
  }
  if (!hasResponseDeadline(evaluation)) {
    reasons.push('Debes establecer una fecha límite de respuesta.')
  }
  return reasons
}

export function isReadyToRequestApproval(evaluation: EvaluationDetailResponse): boolean {
  return requestApprovalPreconditionReasons(evaluation).length === 0
}
