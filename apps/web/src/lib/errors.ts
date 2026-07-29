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
    case 409:
      return {
        kind: 'conflict',
        message:
          'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
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
