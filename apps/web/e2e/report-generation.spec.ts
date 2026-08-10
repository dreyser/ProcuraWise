import { test, expect, type Page } from '@playwright/test'

import { checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

/** Same helper as ai-requirement-suggestions.spec.ts / evaluation-wizard.spec.ts. */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

/**
 * Fase 23 (backlog criterio de aceptación: "Cada reporte se genera como job
 * asíncrono y sigue el contrato de polling"). Proves the create-report
 * request and the ADR 0012 polling wiring work against the real running API.
 *
 * Scoping note (same as ai-requirement-suggestions.spec.ts): `make test-e2e`
 * doesn't start a worker process, so a report triggered here has nothing to
 * process it and stays `queued` indefinitely, by design. This spec verifies
 * the trigger succeeds and the UI enters its polling/loading state against
 * the real server; the succeeded -> download path is covered by the Vitest
 * component test (ReportsPage.test.tsx) instead, where the job status can be
 * mocked deterministically.
 */
test.describe('Reportes (Fase 23)', () => {
  test('owner triggers a report and sees it start generating', async ({ page }) => {
    const evaluationName = `RFP con reportes ${Date.now()}`

    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)

    await page.getByRole('link', { name: 'Nueva evaluación' }).click()
    await page.waitForURL('**/evaluations/new', wait)
    await page.getByLabel('Nombre').fill(evaluationName)
    await page.getByRole('button', { name: 'Crear y continuar' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
    const evaluationId = page.url().split('/evaluations/')[1].split('/wizard')[0]

    // page.goto() would force a full reload, losing the in-memory-only JWT
    // (AUTH-PROD: never persisted) and bouncing back to /login - navigate
    // client-side via the evaluations list + tab nav instead, same pattern
    // as every other authenticated-route spec in this suite.
    await page.getByRole('link', { name: 'Evaluaciones' }).click()
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name: evaluationName }).click()
    await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
    await page.getByRole('link', { name: 'Reportes' }).click()
    await page.waitForURL(`**/evaluations/${evaluationId}/reports`, wait)
    await expect(page.getByRole('heading', { name: 'Generar reporte' })).toBeVisible()

    // rfp_document is available from draft (no readiness gate) - default
    // selection, no need to change the type Select.
    await expect(page.getByRole('button', { name: 'Generar' })).toBeEnabled()
    await page.getByRole('button', { name: 'Generar' }).click()

    await expect(page.getByText('Generando reporte…')).toBeVisible()
    // A queued job with nothing processing it must never surface as an error.
    await expect(page.getByRole('alert')).toHaveCount(0)

    await checkA11y(page)
  })
})
