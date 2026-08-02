import { test, expect } from '@playwright/test'

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
