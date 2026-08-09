import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await submitLoginForm(page, email)
}

/** Use when the page has already been redirected to /login?next=... by
 * RequireAuth (e.g. after a hard navigation lost the in-memory session) -
 * navigating to a bare /login again would discard that ?next= and send the
 * post-login redirect to the role's default home instead of back to the
 * originally requested page. */
async function reLoginAtCurrentLoginPage(page: Page, email: string) {
  await submitLoginForm(page, email)
}

async function submitLoginForm(page: Page, email: string) {
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

/**
 * Fase 25 (billing/admin, ADR 0025) backlog acceptance criterion: "Cobro de
 * prueba exitoso en modo sandbox". This spec demonstrates the in-app half
 * of that flow end to end against LocalPaymentProvider (no network, no
 * Stripe account) - the real Stripe test-mode sandbox charge itself is
 * verified separately via a manual demo (see docs/operations/deployment.md
 * and the stripe_sandbox pytest marker), same established limitation
 * already documented for the AI/report/notification job specs (this file
 * proves the wiring, not the external provider).
 *
 * tenant_admin (tenant-admin.a@dev.procurawise.local) has no access to
 * /evaluations - the evaluation_id it pays for is first read off the URL
 * by owner.a, exactly as a real evaluation_owner would relay it.
 */
test('tenant_admin pays for an evaluation end to end via the local checkout simulator', async ({
  page,
}) => {
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1]
  expect(evaluationId).toBeTruthy()

  await loginAsBuyer(page, 'tenant-admin.a@dev.procurawise.local')
  await page.waitForURL('**/billing', wait)

  await page.getByLabel('ID de la evaluación').fill(evaluationId)
  await page.getByRole('button', { name: 'Pagar' }).click()

  // "Pagar" does a hard browser navigation through the backend's local
  // Checkout simulator (window.location.href, then a real HTTP redirect
  // back) - the same kind of top-level navigation a real Stripe Checkout
  // redirect would do. Since JWTs live only in memory (AUTH-PROD scope
  // decision #2, no persisted session), that hard navigation resets the SPA
  // and the buyer session is lost - RequireAuth correctly bounces to /login,
  // preserving the destination via ?next=. Re-authenticating lands back on
  // the success page, now with a live session, so polling GET
  // /billing/purchases/{id} can confirm "paid".
  await page.waitForURL(/\/login\?next=.*billing%2Fcheckout%2Fsuccess.*/, wait)
  await reLoginAtCurrentLoginPage(page, 'tenant-admin.a@dev.procurawise.local')
  await page.waitForURL(/\/billing\/checkout\/success\?purchase_id=.+/, wait)
  await expect(page.getByRole('heading', { name: 'Pago confirmado' })).toBeVisible()

  await page.getByRole('link', { name: 'Volver a Facturación' }).click()
  await page.waitForURL('**/billing', wait)
  // Scoped to this evaluation's own row - admin-console.spec.ts pays for a
  // different evaluation in the same tenant and may run in the same browser
  // session before this spec, so a bare getByText('Pagada') can match more
  // than one row.
  const row = page.getByRole('row', { name: new RegExp(evaluationId) })
  await expect(row).toBeVisible()
  await expect(row.getByText('Pagada')).toBeVisible()
})
