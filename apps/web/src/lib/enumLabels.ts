// Presentation-layer translation only (brief §2): the wire values below are
// the exact enums the backend contract uses and must never change to match
// these labels.

export const evaluationStatusLabels = {
  draft: 'Borrador',
  collecting_responses: 'Recibiendo propuestas',
  evaluating: 'En evaluación',
  completed: 'Completada',
} as const satisfies Record<string, string>

export const proposalStatusLabels = {
  draft: 'Borrador',
  submitted: 'Enviada',
} as const satisfies Record<string, string>

export const dimensionLabels = {
  functional: 'Funcional',
  technical: 'Técnico',
  economic: 'Económico',
} as const satisfies Record<string, string>

export const priorityLabels = {
  mandatory: 'Obligatorio',
  important: 'Importante',
  desirable: 'Deseable',
} as const satisfies Record<string, string>

export const responseTypeLabels = {
  compliant_status: 'Cumplimiento',
  text: 'Texto',
  single_choice: 'Selección única',
  multi_choice: 'Selección múltiple',
  number: 'Número',
  percentage: 'Porcentaje',
  date: 'Fecha',
  url: 'URL',
  comment: 'Comentario',
  currency: 'Monto',
} as const satisfies Record<string, string>

export const compliantStatusLabels = {
  compliant: 'Cumple',
  partially_compliant: 'Cumple parcialmente',
  non_compliant: 'No cumple',
} as const satisfies Record<string, string>

export const roleLabels = {
  evaluation_owner: 'Responsable de evaluación',
  evaluator_functional: 'Evaluador funcional',
  evaluator_technical: 'Evaluador técnico',
  evaluator_economic: 'Evaluador económico',
  internal_collaborator: 'Colaborador interno',
  approver: 'Aprobador',
  tenant_admin: 'Administrador del cliente',
  vendor_contact: 'Contacto de proveedor',
  // Fase 25 (billing/admin, ADR 0025) - previously absent, would have
  // rendered as the raw string "platform_admin" (translate()'s fallback).
  platform_admin: 'Administrador de plataforma',
} as const satisfies Record<string, string>

export const assignmentStatusLabels = {
  not_started: 'Sin iniciar',
  in_progress: 'En progreso',
  completed: 'Completado',
} as const satisfies Record<string, string>

export const scoringStatusLabels = {
  incomplete: 'Calificación incompleta',
  complete: 'Calificación completa',
} as const satisfies Record<string, string>

export const approvalStatusLabels = {
  not_requested: 'Sin solicitar',
  pending: 'Aprobación pendiente',
  approved: 'Aprobada',
  rejected: 'Rechazada',
} as const satisfies Record<string, string>

// Fase 18 (evaluación asistida por IA, ADR 0022) - matches
// ai.schemas.RiskFlag exactly.
export const riskFlagLabels = {
  incomplete_answer: 'Respuesta incompleta',
  evasive_answer: 'Respuesta evasiva',
  contradictory_answer: 'Respuesta contradictoria',
  missing_evidence: 'Sin evidencia suficiente',
  contractual_risk: 'Riesgo contractual',
} as const satisfies Record<string, string>

// Fase 19 (ADR 0008, spec §8.1) - matches tco.models.CostCategory exactly.
export const costCategoryLabels = {
  initial: 'Iniciales',
  recurring: 'Recurrentes',
  variable_extraordinary: 'Variables y extraordinarios',
} as const satisfies Record<string, string>

// Fase 19 (spec §8.2) - matches tco.models.CostType exactly.
export const costTypeLabels = {
  one_time: 'Único',
  recurring: 'Recurrente',
  variable: 'Variable',
} as const satisfies Record<string, string>

// Fase 20 (ADR 0009) - the 5+5 fixed economic criterion keys, matching
// evaluations.models.DEFAULT_COMMERCIAL_WEIGHTS/DEFAULT_RISK_WEIGHTS
// exactly. Criteria are fixed (not user-authored), so a closed label map is
// appropriate here the same way dimensionLabels/priorityLabels are.
export const economicCriterionLabels = {
  payment_terms: 'Pago y plazo',
  price_protection: 'Protección de precio',
  contractual_flexibility: 'Flexibilidad contractual',
  discounts_incentives: 'Descuentos e incentivos',
  billing_transparency: 'Transparencia y facturación',
  variable_cost_exposure: 'Exposición a costos variables',
  increases_indexation: 'Incrementos e indexación',
  assumptions_exclusions: 'Supuestos y exclusiones',
  fx_fiscal_regulatory: 'Exposición cambiaria y fiscal',
  exit_portability_lockin: 'Salida y portabilidad',
} as const satisfies Record<string, string>

// Fase 21 (ADR 0013) - matches proposals.models.ProposalAnswerVersionStatus
// exactly. A ProposalAnswer always maps 1:1 to a Requirement that can never
// be removed, so "removed" is not a valid answer status (see costItemStatusLabels).
export const answerStatusLabels = {
  inherited: 'Heredada',
  modified: 'Modificada',
} as const satisfies Record<string, string>

// Fase 21 (ADR 0013) - matches tco.models.CostItemVersionStatus exactly.
export const costItemStatusLabels = {
  inherited: 'Heredado',
  modified: 'Modificado',
  removed: 'Eliminado',
} as const satisfies Record<string, string>

// Fase 22 (plan Bloqueante #1, Opcion B) - matches decisions.models.
// DecisionStatus exactly. Same 4-value shape as approvalStatusLabels
// (rejected is not terminal), but this is the decision's own, independent
// approval act - never Evaluation.approval_status.
export const decisionStatusLabels = {
  not_requested: 'Sin solicitar',
  pending: 'Aprobación pendiente',
  approved: 'Aprobada',
  rejected: 'Rechazada',
} as const satisfies Record<string, string>

// Fase 22 - matches decisions.models.DecisionOutcome exactly.
export const decisionOutcomeLabels = {
  selected: 'Proveedor seleccionado',
  void: 'Proceso declarado desierto',
} as const satisfies Record<string, string>

// Fase 23 (ADR 0023) - matches reports.models.ReportType exactly.
export const reportTypeLabels = {
  rfp_document: 'Documento formal de RFP',
  requirements_matrix: 'Matriz de requerimientos',
  vendor_comparison: 'Comparativo de proveedores',
  scoring_detail: 'Detalle de scoring',
  risk_analysis: 'Análisis de riesgos',
  tco_breakdown: 'Desglose de TCO',
  decision_record: 'Acta de decisión',
  qna_summary: 'Resumen de preguntas y respuestas',
} as const satisfies Record<string, string>

// Fase 23 - matches reports.models.ReportFormat exactly.
export const reportFormatLabels = {
  pdf: 'PDF',
  xlsx: 'Excel (XLSX)',
  csv: 'CSV',
  docx: 'Word (DOCX)',
} as const satisfies Record<string, string>

// Fase 23 - matches reports.models.ReportStatus exactly (same 4-state shape
// as an AIExecution job, ADR 0012).
export const reportStatusLabels = {
  queued: 'En cola',
  running: 'Generando',
  succeeded: 'Completado',
  failed: 'Fallido',
} as const satisfies Record<string, string>

function translate<T extends Record<string, string>>(map: T, key: string): string {
  return key in map ? map[key as keyof T] : key
}

export const translateEvaluationStatus = (value: string): string =>
  translate(evaluationStatusLabels, value)
export const translateProposalStatus = (value: string): string =>
  translate(proposalStatusLabels, value)
export const translateDimension = (value: string): string => translate(dimensionLabels, value)
export const translatePriority = (value: string): string => translate(priorityLabels, value)
export const translateResponseType = (value: string): string => translate(responseTypeLabels, value)
export const translateCompliantStatus = (value: string): string =>
  translate(compliantStatusLabels, value)
export const translateRole = (value: string): string => translate(roleLabels, value)
export const translateScoringStatus = (value: string): string =>
  translate(scoringStatusLabels, value)
export const translateAssignmentStatus = (value: string): string =>
  translate(assignmentStatusLabels, value)
export const translateApprovalStatus = (value: string): string =>
  translate(approvalStatusLabels, value)
export const translateRiskFlag = (value: string): string => translate(riskFlagLabels, value)
export const translateCostCategory = (value: string): string => translate(costCategoryLabels, value)
export const translateCostType = (value: string): string => translate(costTypeLabels, value)
export const translateEconomicCriterion = (value: string): string =>
  translate(economicCriterionLabels, value)
export const translateAnswerStatus = (value: string): string => translate(answerStatusLabels, value)
export const translateCostItemStatus = (value: string): string =>
  translate(costItemStatusLabels, value)
export const translateDecisionStatus = (value: string): string =>
  translate(decisionStatusLabels, value)
export const translateDecisionOutcome = (value: string): string =>
  translate(decisionOutcomeLabels, value)
export const translateReportType = (value: string): string => translate(reportTypeLabels, value)
export const translateReportFormat = (value: string): string => translate(reportFormatLabels, value)
export const translateReportStatus = (value: string): string => translate(reportStatusLabels, value)

// Fase 24 - matches notifications.models.NotificationEvent exactly (the 8
// events wired per the phase's approved plan, Bloqueante #1 Opcion A).
export const notificationEventLabels = {
  vendor_invited: 'Invitación de proveedor',
  evaluation_published: 'Evaluación publicada',
  qna_question_received: 'Pregunta recibida',
  qna_answer_published: 'Respuesta publicada',
  proposal_submitted: 'Propuesta enviada',
  proposal_reopened: 'Propuesta reabierta',
  approval_requested: 'Aprobación pendiente',
  evaluation_completed: 'Evaluación cerrada',
} as const satisfies Record<string, string>

export const translateNotificationEvent = (value: string): string =>
  translate(notificationEventLabels, value)

// Fase 25 (billing/admin, ADR 0025) - matches billing.models.PurchaseStatus
// exactly (plan Bloqueante #1 Opcion A: one-time per-evaluation purchase
// only, no subscription lifecycle).
export const purchaseStatusLabels = {
  pending: 'Pendiente',
  paid: 'Pagada',
  expired: 'Expirada',
} as const satisfies Record<string, string>

export const translatePurchaseStatus = (value: string): string =>
  translate(purchaseStatusLabels, value)
