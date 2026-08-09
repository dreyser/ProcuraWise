import { describe, expect, it } from 'vitest'
import { isNextPathAllowedForRole, roleHomePath } from '@/app/roleHomePath'

describe('roleHomePath', () => {
  it('sends vendor_contact to the vendor portal', () => {
    expect(roleHomePath('vendor_contact')).toBe('/vendor/proposals')
  })

  it('sends evaluation_owner and evaluator_functional to the buyer evaluations list', () => {
    expect(roleHomePath('evaluation_owner')).toBe('/evaluations')
    expect(roleHomePath('evaluator_functional')).toBe('/evaluations')
  })

  it('sends tenant_admin to billing (Fase 25) - it has no access to /evaluations', () => {
    expect(roleHomePath('tenant_admin')).toBe('/billing')
  })
})

describe('isNextPathAllowedForRole', () => {
  it('allows a /vendor path only for vendor_contact', () => {
    expect(isNextPathAllowedForRole('/vendor/proposals/abc', 'vendor_contact')).toBe(true)
    expect(isNextPathAllowedForRole('/vendor/proposals/abc', 'evaluation_owner')).toBe(false)
  })

  it('allows a buyer path only for buyer roles', () => {
    expect(isNextPathAllowedForRole('/evaluations/abc', 'evaluation_owner')).toBe(true)
    expect(isNextPathAllowedForRole('/evaluations/abc', 'evaluator_functional')).toBe(true)
    expect(isNextPathAllowedForRole('/evaluations/abc', 'vendor_contact')).toBe(false)
  })

  it('regression: a stale ?next= from a previous actor never leaks into an incompatible role', () => {
    // This is the exact bug found during Bloque 1 verification: selecting a
    // vendor actor while a buyer-route `next` was still in the URL used to
    // send the vendor into a buyer page, which then bounced to /unauthorized.
    const staleBuyerNext = '/evaluations/507f1f77bcf86cd799439011/requirements'
    expect(isNextPathAllowedForRole(staleBuyerNext, 'vendor_contact')).toBe(false)
  })
})
