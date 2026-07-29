import { test, expect } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }

/**
 * A route guard hiding a link/redirecting is only UX (brief §27) - the real
 * authorization boundary is the backend. This proves the backend actually
 * rejects a vendor_contact actor from a buyer-only endpoint with a real
 * HTTP 403, by issuing the request directly rather than only checking that
 * the UI bounced to /unauthorized.
 */
test('isolation: vendor_contact is rejected by the backend (403), not just redirected by the UI', async ({
  page,
}) => {
  await page.goto('/')
  await page.waitForURL('**/dev/select-actor**', wait)
  await page.getByRole('button', { name: /Vendor Contact A/ }).click()
  await page.waitForURL('**/vendor/proposals', wait)

  // UI-level guard.
  await page.goto('/evaluations')
  await page.waitForURL('**/unauthorized', wait)

  // Backend-level guard: same actor, a direct call to the buyer endpoint.
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

  expect(status).toBe(403)
})
