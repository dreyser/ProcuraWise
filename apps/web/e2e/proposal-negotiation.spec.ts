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
  await page.getByLabel('Peso (%)').fill('100')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico negociación')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso (%)').fill('100')
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
  // as "Calificar"/"Evaluación comercial").
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

/**
 * UAT-16 (remediación R1B): reopening one vendor's submitted proposal moves
 * `evaluation.status` from "evaluating" back to "collecting_responses" -
 * `ProposalsPage.tsx` used to gate the whole "Acciones" column (including
 * every OTHER vendor's own "Reabrir para negociación" control) on
 * `evaluation.status === 'evaluating'` only, so reopening vendor A hid
 * vendor B's controls too, even though the backend never blocked B. This
 * spec proves two vendors can be in independent states (one reopened, one
 * still on its original submission) at the same time.
 */
test('Negociación (UAT-16): reabrir la propuesta de un proveedor no oculta las acciones de otro', async ({
  page,
}) => {
  const evaluationName = `RFP multi-proveedor ${Date.now()}`
  const vendorBEmail = `e2e.vendor.uat16.${Date.now()}@dev.procurawise.local`

  // 1. Owner: evaluación con un requerimiento por dimensión, dos
  // proveedores vinculados (uno ya sembrado, uno nuevo dado de alta en el
  // wizard mismo - mismo flujo que evaluation-wizard.spec.ts).
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
  await page.getByLabel('Título').fill('Req funcional UAT-16')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso (%)').fill('100')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico UAT-16')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso (%)').fill('100')
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

  await page.getByLabel('Nombre del proveedor').fill('Proveedor Dos UAT-16')
  await page.getByLabel('Correo del contacto principal').fill(vendorBEmail)
  await page.getByLabel('Nombre del contacto principal').fill('Contacto Dos')
  await page.getByRole('button', { name: 'Crear proveedor e invitar' }).click()
  await expect(page.getByText(/Proveedores vinculados \(2 \/ \d+\)/)).toBeVisible()
  const inviteCode = page.locator('code')
  await expect(inviteCode).toBeVisible()
  const inviteUrl = await inviteCode.textContent()
  const token = new URL(inviteUrl!).searchParams.get('token')
  expect(token).toBeTruthy()
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

  // 2. Proveedor Dos: acepta la invitación y limpia el gate de Agreements.
  await page.goto(`/vendor/accept-invitation?token=${token}`)
  await page.getByLabel('Contraseña', { exact: true }).fill('e2e-vendor-uat16-password-123')
  await page.getByLabel('Confirma tu contraseña').fill('e2e-vendor-uat16-password-123')
  await page.getByRole('button', { name: 'Crear acceso' }).click()
  const ndaSection = page.getByText('Acuerdo de confidencialidad (NDA)').locator('..')
  await ndaSection.getByRole('checkbox').check()
  await ndaSection.getByRole('button', { name: 'Aceptar' }).click()
  const coiSection = page.getByText('Declaración de conflicto de interés').locator('..')
  await coiSection.getByRole('checkbox').check()
  await coiSection.getByRole('button', { name: 'Aceptar' }).click()
  await expect(page.getByRole('heading', { name: 'Mis propuestas' })).toBeVisible()

  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)
  await requirementCard(page, 'Req funcional UAT-16').getByRole('textbox').first().fill('B func')
  await requirementCard(page, 'Req funcional UAT-16').getByRole('textbox').first().blur()
  await requirementCard(page, 'Req técnico UAT-16').getByRole('textbox').first().fill('B tech')
  await requirementCard(page, 'Req técnico UAT-16').getByRole('textbox').first().blur()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()
  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // 3. Proveedor Uno: responde y envía también.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)
  await requirementCard(page, 'Req funcional UAT-16').getByRole('textbox').first().fill('A func')
  await requirementCard(page, 'Req funcional UAT-16').getByRole('textbox').first().blur()
  await requirementCard(page, 'Req técnico UAT-16').getByRole('textbox').first().fill('A tech')
  await requirementCard(page, 'Req técnico UAT-16').getByRole('textbox').first().blur()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()
  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // 4. Owner: inicia evaluación (2 propuestas enviadas), reabre SOLO la de
  // Proveedor Uno - la fila de Proveedor Dos debe seguir mostrando su
  // propio botón "Reabrir para negociación", sin haber cambiado de estado.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  const rowOne = page.getByRole('row', { name: /Proveedor Uno/ })
  const rowTwo = page.getByRole('row', { name: /Proveedor Dos UAT-16/ })
  await expect(rowOne.getByRole('button', { name: 'Reabrir para negociación' })).toBeVisible()
  await expect(rowTwo.getByRole('button', { name: 'Reabrir para negociación' })).toBeVisible()

  await rowOne.getByRole('button', { name: 'Reabrir para negociación' }).click()
  await page.getByLabel('Motivo').fill('Negociación solo con Proveedor Uno.')
  await page.getByLabel('Nueva fecha límite de respuesta').fill('2030-06-01')
  await page.getByRole('dialog').getByRole('button', { name: 'Reabrir propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // La evaluación regresó a collecting_responses (efecto colateral real de
  // reopen()) - antes del fix, esto ocultaba la columna Acciones completa.
  await expect(page.getByText('Recibiendo propuestas')).toBeVisible()
  await expect(rowOne.getByText('Ronda 1')).toBeVisible()
  await expect(rowTwo.getByText('Ronda 0')).toBeVisible()
  await expect(rowTwo.getByRole('button', { name: 'Reabrir para negociación' })).toBeVisible()
  await expect(rowTwo.getByRole('link', { name: 'Calificar' })).toBeVisible()

  await checkA11y(page)
})
