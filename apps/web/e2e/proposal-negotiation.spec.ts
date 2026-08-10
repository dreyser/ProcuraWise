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

/** Same disambiguation approach as tco.spec.ts/qna.spec.ts. */
function requirementCard(page: Page, title: string): Locator {
  return page.locator('div.rounded-md.border.border-border.p-4', {
    has: page.getByRole('heading', { name: title, exact: true }),
  })
}

/**
 * Fase 21 (ADR 0013, FR-047, backlog.md fila 21): the journey up to and
 * including the owner reopening a submitted proposal for a single
 * negotiation round, the vendor revising one answer, resubmitting, and the
 * owner reading the Ronda 0 vs Ronda 1 comparison. The finer-grained
 * acceptance criteria - "modificar una respuesta invalida su score" and
 * "TCO nunca mezcla costos entre versiones" - are proven precisely and
 * quickly against the real API in test_negotiation_round_scoring.py (Docker
 * integration), same split already established for TCO freezing in Fase 19
 * (see tco.spec.ts's own comment); this spec only needs a single vendor to
 * prove the UI wiring end to end.
 */
test('Negociación (Fase 21): owner reopens a submitted proposal, vendor revises and resubmits, owner compares rounds', async ({
  page,
}) => {
  const evaluationName = `RFP con negociación ${Date.now()}`

  // 1. Owner: draft evaluation with one requirement per gated dimension,
  // one vendor linked, approved, moved to collecting_responses.
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
  await page.getByLabel('Título').fill('Req funcional negociación')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('40')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico negociación')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('20')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Siguiente' }).click()

  await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toBeVisible()
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

  // 2. Vendor: answer both requirements, capture a cost item, submit
  // Ronda 0.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  const functionalCard = requirementCard(page, 'Req funcional negociación')
  await functionalCard.getByRole('textbox').first().fill('Respuesta funcional inicial.')
  await functionalCard.getByRole('textbox').first().blur()
  const technicalCard = requirementCard(page, 'Req técnico negociación')
  await technicalCard.getByRole('textbox').first().fill('Respuesta técnica inicial.')
  await technicalCard.getByRole('textbox').first().blur()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()

  await page.getByRole('button', { name: 'Agregar partida de costo' }).click()
  await page.getByLabel('Concepto').fill('Licencia anual')
  await page.getByLabel('Unidad de cobro').fill('usuario')
  await page.getByLabel('Cantidad').fill('10')
  await page.getByLabel('Precio unitario').fill('1000')
  await page.getByRole('button', { name: 'Guardar partida' }).click()
  await expect(page.getByText('Licencia anual')).toBeVisible()

  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Esta propuesta ya fue enviada y no puede editarse.')).toBeVisible()

  // 3. Owner: start the evaluation, then reopen the proposal for a single
  // negotiation round with a reason and a new deadline.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  await page.getByRole('button', { name: 'Reabrir para negociación' }).click()
  await page.getByLabel('Motivo').fill('Negociación de precio y alcance.')
  await page.getByLabel('Nueva fecha límite de respuesta').fill('2030-06-01')
  await page.getByRole('dialog').getByRole('button', { name: 'Reabrir propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  // reopen() already advances round 0 -> 1 (plan §12.2) - the row reflects
  // the new round immediately, before the vendor has even resubmitted.
  await expect(page.getByText('Ronda 1')).toBeVisible()

  // 4. Vendor: sees the reopened banner, revises one answer (the other
  // stays inherited), resubmits Ronda 1.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  await expect(
    page.getByText('El comprador reabrió esta propuesta para una ronda de negociación.'),
  ).toBeVisible()
  await expect(page.getByText('Motivo: Negociación de precio y alcance.')).toBeVisible()

  const revisedFunctionalCard = requirementCard(page, 'Req funcional negociación')
  await revisedFunctionalCard.getByRole('textbox').first().fill('Respuesta funcional revisada.')
  await revisedFunctionalCard.getByRole('textbox').first().blur()
  await expect(revisedFunctionalCard.getByText('Modificada')).toBeVisible()

  const untouchedTechnicalCard = requirementCard(page, 'Req técnico negociación')
  await expect(untouchedTechnicalCard.getByText('Heredada')).toBeVisible()

  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Esta propuesta ya fue enviada y no puede editarse.')).toBeVisible()

  // 5. Owner: reopening moved the evaluation back to collecting_responses -
  // starting it again is the same reused transition as after Ronda 0, and
  // is what makes "Comparar rondas" reachable again (same Acciones gate
  // as "Calificar"/"Ver TCO").
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await expect(page.getByText('Ronda 1')).toBeVisible()
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  await page.getByRole('link', { name: 'Comparar rondas' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/versions$/, wait)

  await expect(page.getByText('Respuesta funcional inicial.')).toBeVisible()
  await expect(page.getByText('Respuesta funcional revisada.')).toBeVisible()
  await expect(
    page.getByText('Motivo de la reapertura: Negociación de precio y alcance.'),
  ).toBeVisible()

  await checkA11y(page)
})
