import { test, expect, type Page } from '@playwright/test'

import { checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

/** Same helper/rationale as vertical-slice.spec.ts: buyer auth is real after
 * AUTH-PROD, token lives only in memory, so every `page.goto()` needs a
 * fresh login afterward. */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

async function fillRequirement(
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
 * Closes the coverage gap `current-phase.md` documented for VS-2C:
 * `vertical-slice.spec.ts` only ever starts from the pre-seeded evaluation
 * and never exercises "create evaluation"/"create requirements"/"link
 * vendor" against the real backend on every run. This spec creates a brand
 * new evaluation from scratch through the Fase 10 wizard, entirely against
 * Mongo/Azurite real (Docker), closing that gap permanently.
 */
test.describe('evaluation wizard (Fase 10)', () => {
  test('owner creates an evaluation end to end through the guided wizard', async ({ page }) => {
    const name = `RFP Wizard E2E ${Date.now()}`

    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name: 'Nueva evaluación' }).click()
    await page.waitForURL('**/evaluations/new', wait)

    // Step 1: metadata. POST /evaluations happens on this submit.
    await page.getByLabel('Nombre').fill(name)
    await page.getByRole('button', { name: 'Crear y continuar' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
    await expect(page.getByRole('heading', { name })).toBeVisible()

    // Step 2: requirements - exactly the 40/20 weights start-collection
    // requires server-side, via the real POST /requirements endpoint.
    await fillRequirement(page, 'Funcional', {
      category: 'Core',
      title: 'Gestión de flujos',
      description: 'Debe soportar flujos configurables',
      weight: '40',
    })
    await fillRequirement(page, 'Técnico', {
      category: 'Integración',
      title: 'API REST',
      description: 'Debe exponer una API documentada',
      weight: '20',
    })
    await page.getByRole('button', { name: 'Siguiente' }).click()

    // Step 3: vendors - real catalog from GET /vendor-organizations. The
    // "dar de alta" form (CreateVendorOrganizationForm, already exercised
    // end to end in vendor-onboarding.spec.ts via the standalone /vendors
    // tab) must also be reachable from inside the wizard - a real pilot gap
    // found during Fase 28 UAT: a first-time owner with an empty catalog had
    // no way to create a vendor without leaving the wizard.
    await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Dar de alta un proveedor nuevo' }),
    ).toBeVisible()
    await page.getByRole('button', { name: 'Vincular' }).click()
    await expect(page.getByText('Proveedores vinculados (1 / 6)')).toBeVisible()
    await page.getByRole('button', { name: 'Siguiente' }).click()

    // Step 4: internal approval (Fase 12) - start-collection is now gated on
    // approval_status === "approved", so publishing requires the assigned
    // approver's decision before the owner can proceed. Every navigation
    // below is an in-app link click, never `page.goto` - the buyer access
    // token lives only in memory (AUTH-PROD scope decision #2), and a real
    // browser navigation (unlike a client-side <Link>) reloads the SPA from
    // scratch, wiping it and bouncing back to /login.
    await page.getByLabel('Aprobador').click()
    await page.getByRole('option', { name: 'Aprobador A' }).click()
    await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
    await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
    await page.getByRole('link', { name: 'Aprobación' }).click()
    await page.getByRole('button', { name: 'Aprobar' }).click()
    await expect(page.getByText('Aprobada')).toBeVisible()

    // Owner logs back in and publishes - the real start-collection
    // transition, from the same wizard step-4 button used before Fase 12.
    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    const row = page.getByRole('row').filter({ hasText: name })
    await row.getByRole('link', { name: 'Continuar configuración' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
    await page.getByRole('button', { name: 'Iniciar recepción de propuestas' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Iniciar recepción' }).click()

    await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
    await expect(page.getByText('Recibiendo propuestas')).toBeVisible()
  })

  test('a fresh login resumes the wizard at the step derived from what was already saved', async ({
    page,
  }) => {
    const name = `RFP Wizard Reload ${Date.now()}`

    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name: 'Nueva evaluación' }).click()
    await page.getByLabel('Nombre').fill(name)
    await page.getByRole('button', { name: 'Crear y continuar' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

    // Only the functional requirement is added - weights stay incomplete on
    // purpose, so the resumed step must be 2, not 3 or 4.
    await fillRequirement(page, 'Funcional', {
      category: 'Core',
      title: 'Gestión de flujos',
      description: 'Debe soportar flujos configurables',
      weight: '40',
    })

    // Simulates the session boundary a real page reload causes: the buyer
    // access token lives only in memory (AUTH-PROD scope decision #2), so
    // any full navigation - including F5 - always forces a fresh login.
    // There is no persisted `wizard_step` anywhere to lose or keep; what
    // must survive is the already-saved requirement itself.
    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)

    const row = page.getByRole('row').filter({ hasText: name })
    await row.getByRole('link', { name: 'Continuar configuración' }).click()

    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
    await expect(page.getByRole('heading', { name })).toBeVisible()
    await expect(page.getByText('Gestión de flujos')).toBeVisible()
    // Still on step 2 - the vendor-linking step's own heading isn't shown.
    await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toHaveCount(0)

    await checkA11y(page)
  })
})
