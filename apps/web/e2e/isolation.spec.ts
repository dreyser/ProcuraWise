import { test, expect } from '@playwright/test'

import { checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }
const DEV_VENDOR_PASSWORD = 'dev-vendor-password-2026'

/**
 * A route guard hiding a link/redirecting is only UX (brief §27) - the real
 * authorization boundary is the backend. This proves the backend actually
 * rejects a vendor_contact actor from a buyer-only endpoint with a real
 * HTTP error, by issuing the request directly (with the vendor's real JWT)
 * rather than only checking that the UI bounced away.
 *
 * Fase 15: vendor_contact authenticates via a real login (token_use=
 * vendor_access), a completely separate credential from the buyer's - not
 * persisted anywhere the page can read back (no sessionStorage, unlike the
 * interim mechanism this replaces), so the token is captured here straight
 * off the login network response instead.
 */
test('isolation: vendor_contact is rejected by the backend, not just redirected by the UI', async ({
  page,
}) => {
  await page.goto('/vendor/login')
  await page.getByLabel('Correo').fill('vendor.a@dev.procurawise.local')
  await page.getByLabel('Contraseña').fill(DEV_VENDOR_PASSWORD)
  const [loginApiResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/vendor-auth/login')),
    page.getByRole('button', { name: 'Entrar' }).click(),
  ])
  const { access_token: vendorAccessToken } = (await loginApiResponse.json()) as {
    access_token: string
  }
  expect(vendorAccessToken).toBeTruthy()
  await page.waitForURL('**/vendor/proposals', wait)

  // UI-level guard: a vendor_contact actor has no buyer credentials at all
  // (a completely separate mechanism, not just a wrong role) - BuyerLayout's
  // RequireAuth sees an anonymous buyer session and sends it to /login, not
  // /unauthorized (that redirect is reserved for a real, authenticated buyer
  // whose role doesn't match a route's allowed roles - see app/guards.tsx).
  await page.goto('/evaluations')
  await page.waitForURL('**/login**', wait)
  await checkA11y(page)

  // Backend-level guard: the vendor's own real JWT, presented directly to a
  // buyer-only endpoint. Buyer routes only accept a token with
  // token_use="access" (shared.context.require_role via
  // identity.jwt_provider.get_current_context) - a vendor_access token is
  // structurally rejected (401), not merely role-checked away (403).
  const status = await page.evaluate(async (token) => {
    const response = await fetch('/api/v1/evaluations', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.status
  }, vendorAccessToken)

  expect(status).toBe(401)
})

/**
 * UAT-10 (R1C): the single generic endpoint above proves the token_use gate
 * is real, but scoring/economic-assessment/decisions are the routes closest
 * to the data a vendor would most want to see early (its own evaluation
 * scores) - this makes the coverage explicit for exactly those three route
 * families instead of relying on the reader to trust the gate is uniform
 * across every buyer router. No real evaluation/proposal is needed: the
 * token_use check runs as a FastAPI dependency and rejects the request
 * before the path parameters are ever used to look anything up, so a
 * placeholder id is enough to prove the boundary holds for these routes too.
 */
test('isolation: vendor_contact is rejected from scoring, economic-assessment, and decisions routes', async ({
  page,
}) => {
  await page.goto('/vendor/login')
  await page.getByLabel('Correo').fill('vendor.a@dev.procurawise.local')
  await page.getByLabel('Contraseña').fill(DEV_VENDOR_PASSWORD)
  const [loginApiResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/vendor-auth/login')),
    page.getByRole('button', { name: 'Entrar' }).click(),
  ])
  const { access_token: vendorAccessToken } = (await loginApiResponse.json()) as {
    access_token: string
  }
  expect(vendorAccessToken).toBeTruthy()
  await page.waitForURL('**/vendor/proposals', wait)

  const placeholderId = 'isolation-check'
  const requests = [
    {
      label: 'scoring write',
      method: 'PUT',
      url: `/api/v1/evaluations/${placeholderId}/proposals/${placeholderId}/scores/${placeholderId}`,
      body: { score: 5 },
    },
    {
      label: 'economic-assessment read',
      method: 'GET',
      url: `/api/v1/evaluations/${placeholderId}/proposals/${placeholderId}/economic-assessment`,
    },
    {
      label: 'economic-assessment write',
      method: 'PUT',
      url: `/api/v1/evaluations/${placeholderId}/proposals/${placeholderId}/economic-assessment`,
      body: { commercial_scores: [], risk_scores: [] },
    },
    {
      label: 'decisions read',
      method: 'GET',
      url: `/api/v1/evaluations/${placeholderId}/decision`,
    },
    {
      label: 'decisions approve (write)',
      method: 'POST',
      url: `/api/v1/evaluations/${placeholderId}/decision/approve`,
      body: {},
    },
  ]

  const statuses = await page.evaluate(
    async ({ token, requests: reqs }) => {
      const results: number[] = []
      for (const req of reqs) {
        const response = await fetch(req.url, {
          method: req.method,
          headers: {
            Authorization: `Bearer ${token}`,
            ...(req.body ? { 'Content-Type': 'application/json' } : {}),
          },
          body: req.body ? JSON.stringify(req.body) : undefined,
        })
        results.push(response.status)
      }
      return results
    },
    { token: vendorAccessToken, requests },
  )

  requests.forEach((req, index) => {
    expect(statuses[index], `${req.label} (${req.method} ${req.url})`).toBe(401)
  })
})
