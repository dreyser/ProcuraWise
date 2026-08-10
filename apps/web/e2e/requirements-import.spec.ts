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
 * Fase 23 (backlog fila 23: "import Excel/CSV con preview+mapeo"). Unlike
 * report-generation.spec.ts, this flow is fully synchronous (no worker
 * involved - `RequirementImportService.confirm` writes directly via
 * `add_requirements_bulk`), so this spec verifies the entire
 * upload -> preview/mapping -> confirm -> created Requirement path against
 * the real running API, not just the trigger.
 */
test('Import de requerimientos (Fase 23): sube un CSV, revisa el mapeo y confirma', async ({
  page,
}) => {
  const evaluationName = `RFP con import ${Date.now()}`

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
  await page.getByRole('link', { name: 'Requerimientos' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/requirements`, wait)
  await page.getByRole('button', { name: 'Importar Excel/CSV' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  const csv = [
    'Titulo,Dimension,Categoria,Descripcion,Prioridad,Peso,Obligatorio',
    'Req E2E importado,functional,Core,Descripcion del requerimiento,important,40,false',
  ].join('\n')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'requerimientos.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv, 'utf-8'),
  })

  await expect(page.getByText('Vista previa (1 filas)')).toBeVisible()
  await expect(page.getByText('Req E2E importado')).toBeVisible()
  const confirmButton = page.getByRole('button', { name: 'Confirmar importación' })
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()

  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('table').getByRole('cell', { name: 'Req E2E importado' })).toBeVisible()

  await checkA11y(page)
})
