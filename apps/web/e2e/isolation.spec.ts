import { test, expect } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }

/**
 * A route guard hiding a link/redirecting is only UX (brief §27) - the real
 * authorization boundary is the backend. This proves the backend actually
 * rejects a vendor_contact actor from a buyer-only endpoint with a real
 * HTTP error, by issuing the request directly rather than only checking that
 * the UI bounced away.
 *
 * vendor_contact stays on the interim dev-header mechanism until Fase 15
 * (AUTH-PROD scope decision #1) - visited directly at /dev/select-actor,
 * since `/` now defaults to the real buyer login (/login) instead.
 */
test('isolation: vendor_contact is rejected by the backend, not just redirected by the UI', async ({
  page,
}) => {
  await page.goto('/dev/select-actor')
  await page.getByRole('button', { name: /Vendor Contact A/ }).click()
  await page.waitForURL('**/vendor/proposals', wait)

  // UI-level guard: a vendor_contact actor has no buyer credentials at all
  // (a completely separate mechanism after AUTH-PROD, not just a wrong
  // role) - BuyerLayout's RequireAuth sees an anonymous buyer session and
  // sends it to /login, not /unauthorized (that redirect is reserved for a
  // real, authenticated buyer whose role doesn't match a route's allowed
  // roles - see app/guards.tsx).
  await page.goto('/evaluations')
  await page.waitForURL('**/login**', wait)

  // Backend-level guard: same vendor actor, a direct call to the buyer
  // endpoint. Buyer routes only accept a real `Authorization: Bearer` access
  // token after AUTH-PROD (require_role no longer reads X-Dev-Membership-Id
  // at all for them) - a vendor_contact actor has no way to obtain one, so
  // this now fails at authentication (401) rather than at role-checking
  // (403), a strictly stronger isolation guarantee than before.
  const membershipId = await page.evaluate(() =>
    window.sessionStorage.getItem('procurawise.dev.membershipId'),
  )
  expect(membershipId).toBeTruthy()

  const status = await page.evaluate(async (id) => {
    const response = await fetch('/api/v1/evaluations', {
      headers: { 'X-Dev-Membership-Id': id as string },
    })
    return response.status
  }, membershipId)

  expect(status).toBe(401)
})
