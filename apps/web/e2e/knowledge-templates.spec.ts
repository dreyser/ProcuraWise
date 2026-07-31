import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

/** Same helper/rationale as evaluation-wizard.spec.ts: buyer auth is real
 * after AUTH-PROD, token lives only in memory, so every `page.goto()` needs
 * a fresh login afterward. */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

async function addTemplateItem(
  page: Page,
  dimensionHeading: 'Funcional' | 'Técnico',
  fields: { category: string; title: string; description: string; weight: string },
) {
  const section = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: dimensionHeading, exact: true }) })
  await section.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill(fields.category)
  await page.getByLabel('Título').fill(fields.title)
  await page.getByLabel('Descripción', { exact: true }).fill(fields.description)
  await page.getByLabel('Peso').fill(fields.weight)
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)
}

/**
 * Fase 11 (biblioteca de requerimientos, sin IA): a buyer saves a reusable
 * template once, then applies it to a brand new evaluation in one action -
 * the acceptance criterion ("plantilla aplicable a nueva evaluación, reduce
 * alta manual") end to end against Mongo real (Docker), not just via API
 * tests.
 */
test.describe('knowledge templates (Fase 11)', () => {
  test('owner creates a template and applies it to a new evaluation', async ({ page }) => {
    const templateName = `Plantilla E2E ${Date.now()}`
    const evaluationName = `RFP con plantilla ${Date.now()}`

    // Every navigation below is an in-app <Link> click, never `page.goto` -
    // the buyer access token lives only in memory (AUTH-PROD scope decision
    // #2), and a real browser navigation reloads the SPA from scratch,
    // wiping it and bouncing back to /login.
    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)

    // Create the template with one functional and one technical item.
    await page.getByRole('link', { name: 'Plantillas' }).click()
    await page.waitForURL('**/knowledge-templates', wait)
    await page.getByRole('button', { name: 'Nueva plantilla' }).click()
    await page.getByLabel('Nombre').fill(templateName)
    await page.getByRole('button', { name: 'Crear plantilla' }).click()
    await page.waitForURL(/\/knowledge-templates\/[a-f0-9]+$/, wait)
    await expect(page.getByRole('heading', { name: templateName })).toBeVisible()

    await addTemplateItem(page, 'Funcional', {
      category: 'Core',
      title: 'Gestión de flujos',
      description: 'Debe soportar flujos configurables',
      weight: '40',
    })
    await addTemplateItem(page, 'Técnico', {
      category: 'Integración',
      title: 'API REST',
      description: 'Debe exponer una API documentada',
      weight: '20',
    })

    // Create a new evaluation through the wizard and apply the template at
    // Step 2 instead of adding requirements manually.
    await page.getByRole('link', { name: 'Evaluaciones' }).click()
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name: 'Nueva evaluación' }).click()
    await page.waitForURL('**/evaluations/new', wait)
    await page.getByLabel('Nombre').fill(evaluationName)
    await page.getByRole('button', { name: 'Crear y continuar' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

    await page.getByLabel('Plantilla', { exact: true }).click()
    await page.getByRole('option', { name: new RegExp(`^${templateName} \\(2\\)$`) }).click()
    await page.getByRole('button', { name: 'Aplicar plantilla' }).click()

    await expect(page.getByText('Gestión de flujos')).toBeVisible()
    await expect(page.getByText('API REST')).toBeVisible()

    // The applied weights (40 functional + 20 technical) satisfy readiness
    // without any further manual entry - "Siguiente" is enabled.
    await expect(page.getByRole('button', { name: 'Siguiente' })).toBeEnabled()
  })
})
