import { test, expect, type Page, type Locator } from '@playwright/test'

import { checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'
const DEV_VENDOR_PASSWORD = 'dev-vendor-password-2026'

async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

async function loginAsVendor(page: Page, email: string) {
  await page.goto('/vendor/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_VENDOR_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/vendor/login'), wait)
}

/** Same disambiguation approach as ai-score-suggestions.spec.ts/qna.spec.ts -
 * the requirement card also hosts evidence upload/question-thread controls
 * whose own textbox would otherwise collide with a page-wide query. */
function requirementCard(page: Page, title: string): Locator {
  return page.locator('div.rounded-md.border.border-border.p-4', {
    has: page.getByRole('heading', { name: title, exact: true }),
  })
}

/**
 * Fase 19 (ADR 0008, backlog.md fila 19): the journey up to and including
 * the buyer reading a submitted proposal's frozen TCO. The finer-grained
 * acceptance criterion itself - "TCO recalculado no cambia al actualizar
 * FXRate después de publicación" - is proven precisely and quickly against
 * the real API in test_proposal_submit_tco_freeze.py (Docker integration),
 * same split already established for AI job completion (Fase 13/18); this
 * spec only needs a single-currency cost item (matching the evaluation's
 * default MXN base currency) so it never depends on any FXRate existing.
 */
test('TCO (Fase 19): vendor captures a cost item and submits, owner reads the frozen TCO', async ({
  page,
}) => {
  const evaluationName = `RFP con TCO ${Date.now()}`

  // 1. Owner: draft evaluation with one requirement per gated dimension,
  // one vendor linked, approved, moved to collecting_responses - same setup
  // shape as ai-score-suggestions.spec.ts/qna.spec.ts.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(evaluationName)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1].split('/wizard')[0]

  const functionalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Funcional', exact: true }) })
  await functionalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req funcional TCO')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('40')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico TCO')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('20')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Siguiente' }).click()

  await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toBeVisible()
  // Other specs in this same suite run may have already onboarded extra
  // vendor orgs into the shared catalog (e.g. qna.spec.ts) - this must link
  // the original seeded vendor org specifically, since the next step logs
  // in as vendor.a@dev.procurawise.local (a member of "Proveedor Uno (dev)"
  // only, same name qna.spec.ts already relies on for its own assertions).
  await page
    .getByRole('listitem')
    .filter({ hasText: 'Proveedor Uno (dev)' })
    .getByRole('button', { name: 'Vincular' })
    .click()
  await expect(page.getByText(/Proveedores vinculados \(1 \/ \d+\)/)).toBeVisible()
  await page.getByRole('button', { name: 'Siguiente' }).click()

  await page.getByLabel('Aprobador').click()
  await page.getByRole('option', { name: 'Aprobador A' }).click()
  await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
  await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
  await expect(page.getByText('Aprobación pendiente')).toBeVisible()

  await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Aprobación' }).click()
  await page.getByRole('button', { name: 'Aprobar' }).click()
  await expect(page.getByText('Aprobada')).toBeVisible()

  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/vendors`, wait)
  await page.getByRole('button', { name: 'Iniciar recepción de propuestas' }).click()
  await page.getByRole('button', { name: 'Iniciar recepción' }).click()
  await expect(page.getByText('Recibiendo propuestas')).toBeVisible()

  // 2. Vendor: answer both (required-by-default) requirements, capture a
  // single MXN cost item (matching the evaluation's default base currency,
  // so no FXRate needs to exist), see the preview total, then submit.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  const functionalCard = requirementCard(page, 'Req funcional TCO')
  await functionalCard.getByRole('textbox').first().fill('Respuesta funcional.')
  await functionalCard.getByRole('textbox').first().blur()
  const technicalCard = requirementCard(page, 'Req técnico TCO')
  await technicalCard.getByRole('textbox').first().fill('Respuesta técnica.')
  await technicalCard.getByRole('textbox').first().blur()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()

  await page.getByRole('button', { name: 'Agregar partida de costo' }).click()
  await page.getByLabel('Concepto').fill('Licencia anual')
  await page.getByLabel('Unidad de cobro').fill('usuario')
  await page.getByLabel('Cantidad').fill('10')
  await page.getByLabel('Precio unitario').fill('1000')
  await page.getByRole('button', { name: 'Guardar partida' }).click()
  await expect(page.getByText('Licencia anual')).toBeVisible()
  await expect(page.getByText(/TCO estimado/)).toBeVisible()
  await expect(page.getByText('10000.00')).toBeVisible()

  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Esta propuesta ya fue enviada y no puede editarse.')).toBeVisible()

  // 3. Owner: start the evaluation and read the frozen TCO from the
  // proposals list.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  await page.getByRole('link', { name: 'Ver TCO' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/tco$/, wait)

  await expect(page.getByText(/TCO \(1 año\(s\), MXN\)/)).toBeVisible()
  await expect(page.getByText('10000.00').first()).toBeVisible()

  await checkA11y(page)
})
