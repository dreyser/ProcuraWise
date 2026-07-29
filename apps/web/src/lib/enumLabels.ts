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
  evaluator: 'Evaluador',
  vendor_contact: 'Contacto de proveedor',
} as const satisfies Record<string, string>

export const scoringStatusLabels = {
  incomplete: 'Calificación incompleta',
  complete: 'Calificación completa',
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
