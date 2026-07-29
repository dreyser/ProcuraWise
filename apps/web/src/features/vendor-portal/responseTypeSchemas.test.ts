import { describe, expect, it } from 'vitest'
import {
  currencySchema,
  dateSchema,
  numberSchema,
  percentageSchema,
  urlSchema,
} from '@/features/vendor-portal/responseTypeSchemas'

// These mirror the backend's exact rules (proposals/service.py:23,
// validate_answer_value) - client-side validation must never be looser or
// diverge from what the server ultimately enforces.

describe('percentageSchema', () => {
  it('accepts the boundaries 0 and 100', () => {
    expect(percentageSchema.safeParse('0').success).toBe(true)
    expect(percentageSchema.safeParse('100').success).toBe(true)
  })

  it('rejects values outside 0-100', () => {
    expect(percentageSchema.safeParse('-1').success).toBe(false)
    expect(percentageSchema.safeParse('101').success).toBe(false)
  })
})

describe('numberSchema', () => {
  it('accepts a plain numeric string', () => {
    const result = numberSchema.safeParse('120')
    expect(result.success).toBe(true)
    if (result.success) expect(result.data).toBe(120)
  })

  it('rejects a non-numeric string', () => {
    expect(numberSchema.safeParse('not-a-number').success).toBe(false)
  })
})

describe('dateSchema', () => {
  it('accepts a valid ISO date', () => {
    expect(dateSchema.safeParse('2026-07-27').success).toBe(true)
  })

  it('rejects a malformed date', () => {
    expect(dateSchema.safeParse('not-a-date').success).toBe(false)
  })
})

describe('urlSchema', () => {
  it('accepts http and https URLs', () => {
    expect(urlSchema.safeParse('http://example.com').success).toBe(true)
    expect(urlSchema.safeParse('https://example.com').success).toBe(true)
  })

  it('rejects a URL without an http(s) scheme', () => {
    expect(urlSchema.safeParse('ftp://example.com').success).toBe(false)
    expect(urlSchema.safeParse('example.com').success).toBe(false)
  })
})

describe('currencySchema', () => {
  it('accepts a non-negative amount with a real currency code', () => {
    const result = currencySchema.safeParse({ amount: '150.5', currency_code: 'MXN' })
    expect(result.success).toBe(true)
    if (result.success) expect(result.data).toEqual({ amount: 150.5, currency_code: 'MXN' })
  })

  it('accepts USD as the other real backend currency code', () => {
    expect(currencySchema.safeParse({ amount: '10', currency_code: 'USD' }).success).toBe(true)
  })

  it('rejects a negative amount', () => {
    expect(currencySchema.safeParse({ amount: '-1', currency_code: 'MXN' }).success).toBe(false)
  })

  it('rejects a currency_code outside the exact backend set ({MXN, USD})', () => {
    expect(currencySchema.safeParse({ amount: '10', currency_code: 'EUR' }).success).toBe(false)
  })
})
