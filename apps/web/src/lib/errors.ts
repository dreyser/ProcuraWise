import { ApiError } from '@/lib/http'

export type ErrorKind =
  'validation' | 'conflict' | 'forbidden' | 'not_found' | 'business_rule' | 'network' | 'unknown'

export interface NormalizedError {
  kind: ErrorKind
  message: string
  fieldErrors?: Record<string, string>
}

interface FastApiValidationDetail {
  loc: (string | number)[]
  msg: string
}

function extractDetailMessage(data: unknown): string | undefined {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return undefined
}

// UAT-11 (remediación R1A): every 409 used to render the exact same "los
// datos cambiaron" text, even though the backend already returns a distinct
// `detail` string per cause (see e.g. vendor_portal/router.py:216-219,
// qna/router.py:143 - InvalidProposalTransitionError/
// InvalidQuestionTransitionError vs. StaleVersionError). A real conflict
// found during Fase 28 UAT turned out to be "the evaluation never left
// draft," not a version race - the generic message sent the investigation
// down the wrong path first. Known business-rule-transition messages get
// their own actionable copy; anything else (including every genuine
// "stale ... version" case) keeps the original conflict message, since
// those really are "reload and see what changed."
const KNOWN_CONFLICT_DETAILS: Record<string, string> = {
  'evaluation is not collecting_responses':
    'Esta evaluación no está recibiendo respuestas en este momento (el comprador todavía no inició la recepción, o ya avanzó a la fase de calificación). Recarga para confirmar el estado actual.',
  'proposal is not draft': 'Esta propuesta ya fue enviada y no se puede seguir editando.',
  'proposal is not submitted':
    'Esta propuesta todavía no fue enviada, esa acción requiere una propuesta ya enviada.',
  'evaluation is not evaluating':
    'Esta evaluación no está en la fase de calificación en este momento.',
}

function extractFieldErrors(data: unknown): Record<string, string> | undefined {
  if (!data || typeof data !== 'object' || !('detail' in data)) return undefined
  const detail = (data as { detail: unknown }).detail
  if (!Array.isArray(detail)) return undefined

  const fieldErrors: Record<string, string> = {}
  for (const item of detail as FastApiValidationDetail[]) {
    if (!item || !Array.isArray(item.loc)) continue
    const field = [...item.loc].reverse().find((segment) => segment !== 'body')
    if (field === undefined) continue
    fieldErrors[String(field)] = item.msg
  }
  return Object.keys(fieldErrors).length > 0 ? fieldErrors : undefined
}

/**
 * Central error normalization (brief §23): every screen renders from this,
 * never from a raw FastAPI/Pydantic message.
 */
export function normalizeApiError(error: unknown): NormalizedError {
  if (!(error instanceof ApiError)) {
    return {
      kind: 'network',
      message: 'No se pudo conectar con el servidor. Verifica tu conexión e intenta de nuevo.',
    }
  }

  switch (error.status) {
    case 400:
      return {
        kind: 'business_rule',
        message: extractDetailMessage(error.data) ?? 'La operación no cumple una regla de negocio.',
      }
    case 403:
      return { kind: 'forbidden', message: 'No tienes permiso para realizar esta acción.' }
    case 404:
      return { kind: 'not_found', message: 'El recurso solicitado no está disponible.' }
    case 409: {
      const detail = extractDetailMessage(error.data)
      return {
        kind: 'conflict',
        message:
          (detail && KNOWN_CONFLICT_DETAILS[detail]) ??
          'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
      }
    }
    case 422:
      return {
        kind: 'validation',
        message: 'Revisa los campos marcados antes de continuar.',
        fieldErrors: extractFieldErrors(error.data),
      }
    default:
      return { kind: 'unknown', message: 'Ocurrió un error inesperado. Intenta de nuevo.' }
  }
}
