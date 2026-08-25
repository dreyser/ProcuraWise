import { describe, expect, it } from 'vitest'
import { normalizeApiError } from '@/lib/errors'
import { ApiError } from '@/lib/http'

describe('normalizeApiError', () => {
  it('maps a network/unknown error (not an ApiError) to a connectivity message', () => {
    const result = normalizeApiError(new TypeError('Failed to fetch'))
    expect(result.kind).toBe('network')
  })

  it('maps 400 to a business_rule error using the backend detail text', () => {
    const error = new ApiError(400, {
      detail: 'functional requirement weights must sum to 40.0, got 35.0',
    })
    const result = normalizeApiError(error)
    expect(result.kind).toBe('business_rule')
    expect(result.message).toBe('functional requirement weights must sum to 40.0, got 35.0')
  })

  it('maps 403 to forbidden with a fixed, non-technical message', () => {
    const result = normalizeApiError(new ApiError(403, { detail: 'role not permitted' }))
    expect(result.kind).toBe('forbidden')
    expect(result.message).not.toMatch(/role not permitted/)
  })

  it('maps 404 to not_found', () => {
    expect(normalizeApiError(new ApiError(404, undefined)).kind).toBe('not_found')
  })

  it('maps 409 to conflict', () => {
    const result = normalizeApiError(new ApiError(409, { detail: 'stale version' }))
    expect(result.kind).toBe('conflict')
  })

  it('keeps the generic conflict message for a genuine stale-version 409', () => {
    const result = normalizeApiError(new ApiError(409, { detail: 'stale version' }))
    expect(result.message).toBe(
      'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
    )
  })

  it('keeps the generic conflict message when a 409 has no recognized detail', () => {
    const result = normalizeApiError(new ApiError(409, undefined))
    expect(result.kind).toBe('conflict')
    expect(result.message).toBe(
      'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
    )
  })

  it('gives a distinct, actionable message when a 409 means the evaluation is not collecting responses', () => {
    const result = normalizeApiError(
      new ApiError(409, { detail: 'evaluation is not collecting_responses' }),
    )
    expect(result.kind).toBe('conflict')
    expect(result.message).not.toBe(
      'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
    )
    expect(result.message).toMatch(/no está recibiendo respuestas/)
  })

  it('gives a distinct message when a 409 means the proposal is no longer editable', () => {
    const result = normalizeApiError(new ApiError(409, { detail: 'proposal is not draft' }))
    expect(result.message).toMatch(/ya fue enviada/)
  })

  it('maps 422 to validation and extracts per-field messages from Pydantic-style detail', () => {
    const error = new ApiError(422, {
      detail: [
        { loc: ['body', 'name'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'weight'], msg: 'Input should be a valid number', type: 'float_type' },
      ],
    })
    const result = normalizeApiError(error)
    expect(result.kind).toBe('validation')
    expect(result.fieldErrors).toEqual({
      name: 'Field required',
      weight: 'Input should be a valid number',
    })
  })

  it('does not produce fieldErrors when the 422 detail is not an array', () => {
    const result = normalizeApiError(new ApiError(422, { detail: 'not a list' }))
    expect(result.fieldErrors).toBeUndefined()
  })

  it('maps an unmapped status to a generic unknown error', () => {
    expect(normalizeApiError(new ApiError(500, undefined)).kind).toBe('unknown')
  })

  it('never surfaces a raw FastAPI/Pydantic message for statuses with a fixed copy', () => {
    const raw = 'Internal Server Error: Traceback (most recent call last)...'
    const result = normalizeApiError(new ApiError(500, { detail: raw }))
    expect(result.message).not.toContain('Traceback')
  })
})
