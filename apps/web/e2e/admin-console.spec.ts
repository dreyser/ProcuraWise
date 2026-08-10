import { test, expect, type Page } from '@playwright/test'

import { checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'
const DEV_ADMIN_EMAIL = 'platform-admin@dev.procurawise.local'
const DEV_ADMIN_PASSWORD = 'dev-admin-password-2026'

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

async function loginAsAdmin(page: Page) {
  await page.goto('/admin/login')
  await page.getByLabel('Correo').fill(DEV_ADMIN_EMAIL)
  await page.getByLabel('Contraseña').fill(DEV_ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL('**/admin/evaluations', wait)
}

/**
 * Fase 25 (billing/admin, ADR 0025, plan Bloqueante #2 Opcion b) backlog
 * acceptance criterion: "acción admin cross-tenant queda auditada con
 * motivo". This spec demonstrates the entire admin half of that criterion
 * end to end in a real browser: platform_admin logs in with its own real
 * JWT (token_use=admin_access, structurally separate from every buyer/
 * vendor token), the console refuses to fetch anything until a real reason
 * is typed, and the cross-tenant data it then shows spans a tenant this
 * platform_admin session never itself authenticated into. The audit-trail
 * side of "con motivo" (one AuditEvent per record touched, visible on that
 * evaluation's own trail) is proven at the API level in
 * tests/api/test_admin_router.py / test_billing_admin_router.py - no
 * frontend audit-trail viewer exists to check it visually here.
 */
test('platform_admin console: reason gate blocks the query, then shows real cross-tenant evaluations and billing data', async ({
  page,
}) => {
  const uniqueSuffix = Date.now()
  const evaluationName = `RFP Admin Console E2E ${uniqueSuffix}`

  // 1. Comprador: crea una evaluación nueva (identificable de forma única)
  // y paga por ella, para que ambas páginas de la consola tengan datos
  // reales que mostrar, sin depender de otro spec.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(evaluationName)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1].split('/wizard')[0]

  await loginAsBuyer(page, 'tenant-admin.a@dev.procurawise.local')
  await page.waitForURL('**/billing', wait)
  await page.getByLabel('ID de la evaluación').fill(evaluationId)
  await page.getByRole('button', { name: 'Pagar' }).click()

  // Hard navigation through the local Checkout simulator loses the
  // in-memory-only buyer session (AUTH-PROD scope decision #2) - RequireAuth
  // bounces to /login preserving ?next=, same as a real Stripe redirect
  // would. See billing-checkout.spec.ts for the full explanation.
  await page.waitForURL(/\/login\?next=.*billing%2Fcheckout%2Fsuccess.*/, wait)
  await reLoginAtCurrentLoginPage(page, 'tenant-admin.a@dev.procurawise.local')
  await page.waitForURL(/\/billing\/checkout\/success\?purchase_id=.+/, wait)
  await expect(page.getByRole('heading', { name: 'Pago confirmado' })).toBeVisible()

  // 2. platform_admin: sin motivo, no hay datos.
  await loginAsAdmin(page)
  await expect(page.getByRole('button', { name: 'Consultar' })).toBeDisabled()
  await expect(page.getByText(evaluationName)).toHaveCount(0)

  // 3. Con motivo, los datos cross-tenant aparecen.
  await page.getByLabel('Motivo de la consulta').fill('auditoria de cumplimiento')
  await page.getByRole('button', { name: 'Consultar' }).click()
  await expect(page.getByText('Acme Compradora (dev)').first()).toBeVisible()
  await expect(page.getByText(evaluationName)).toBeVisible()
  await expect(page.getByText('Consultando con motivo: auditoria de cumplimiento')).toBeVisible()

  // 4. La misma disciplina de motivo aplica en la página de facturación.
  await page.getByRole('link', { name: 'Facturación' }).click()
  await page.waitForURL('**/admin/billing', wait)
  await expect(page.getByRole('button', { name: 'Consultar' })).toBeDisabled()

  await page.getByLabel('Motivo de la consulta').fill('revision de pagos')
  await page.getByRole('button', { name: 'Consultar' }).click()
  // Scoped to this evaluation's own row - billing-checkout.spec.ts pays for
  // a different evaluation in the same tenant and may run in the same
  // browser session, so a bare getByText('Pagada') can match more than one
  // row.
  const row = page.getByRole('row', { name: new RegExp(evaluationId) })
  await expect(row).toBeVisible()
  await expect(row.getByText('Pagada')).toBeVisible()

  await checkA11y(page)
})
