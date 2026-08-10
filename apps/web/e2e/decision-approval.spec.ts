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

function requirementCard(page: Page, title: string): Locator {
  return page.locator('div.rounded-md.border.border-border.p-4', {
    has: page.getByRole('heading', { name: title, exact: true }),
  })
}

const ECONOMIC_CRITERION_LABELS = [
  'Pago y plazo',
  'Protección de precio',
  'Flexibilidad contractual',
  'Descuentos e incentivos',
  'Transparencia y facturación',
  'Exposición a costos variables',
  'Incrementos e indexación',
  'Supuestos y exclusiones',
  'Exposición cambiaria y fiscal',
  'Salida y portabilidad',
]

/**
 * Fase 22 (backlog.md fila 22, plan Bloqueante #1 Opcion B): the journey
 * from a completed evaluation through selection, an independent decision
 * approver assignment, rejection-with-comment, owner revision and
 * resubmission, approval, and the frozen read-only memo de cierre. Reuses
 * "Aprobador A" as both the publication approver and the decision approver
 * (dev_seed.py only seeds one approver-role account under tenant_a) - both
 * are valid per the founder's resolution (same person or a different one),
 * and the two assignments being genuinely independent fields is proven
 * precisely at the integration level
 * (tests/integration/test_decision_workflow.py,
 * tests/security/test_decision_isolation.py); this spec only needs to prove
 * the UI wiring end to end, same split already established for TCO
 * freezing (tco.spec.ts) and the negotiation round (proposal-negotiation.spec.ts).
 */
test('Decisión (Fase 22): owner selects a vendor, approver rejects then approves, memo de cierre is read-only', async ({
  page,
}) => {
  const evaluationName = `RFP con decisión ${Date.now()}`

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
  await page.getByLabel('Título').fill('Req funcional decisión')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('40')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico decisión')
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

  // 2. Vendor: answer both requirements, capture a cost item, submit.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  const functionalCard = requirementCard(page, 'Req funcional decisión')
  await functionalCard.getByRole('textbox').first().fill('Respuesta funcional.')
  await functionalCard.getByRole('textbox').first().blur()
  const technicalCard = requirementCard(page, 'Req técnico decisión')
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

  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // 3. Owner: start evaluation, then score/assess and complete it - a
  // Decision may only be created once Evaluation.status === "completed"
  // (plan section 10, decision 1).
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  await page.getByRole('link', { name: 'Calificar' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/score$/, wait)
  await expect(page.getByText('Calificados: 0 / 2')).toBeVisible()
  const scoreButtons5 = page.getByRole('radio', { name: '5' })
  const scoreCount = await scoreButtons5.count()
  for (let i = 0; i < scoreCount; i += 1) {
    await scoreButtons5.nth(i).check({ force: true })
  }
  const saveButtons = page.getByRole('button', { name: 'Guardar calificación' })
  const saveCount = await saveButtons.count()
  for (let i = 0; i < saveCount; i += 1) {
    await saveButtons.nth(i).click()
    await expect(page.getByText(`Calificados: ${i + 1} / 2`)).toBeVisible()
  }
  for (const label of ECONOMIC_CRITERION_LABELS) {
    await page.getByRole('radio', { name: `${label}: 3` }).check({ force: true })
  }
  await page.getByRole('button', { name: 'Guardar evaluación económica' }).click()
  await expect(page.getByRole('button', { name: 'Guardar evaluación económica' })).toBeEnabled()
  await expect(page.getByRole('alert')).toHaveCount(0)

  // ScoringPage (a single proposal's view) has no EvaluationTabNav of its
  // own - navigate back via the evaluations list + detail page, same
  // pattern as vertical-slice.spec.ts, rather than assuming "Resultados"
  // is reachable directly from here.
  await page.getByRole('link', { name: 'Evaluaciones' }).click()
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Resultados' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/results`, wait)
  await expect(page.getByText('Estado de calificación: Calificación completa')).toBeVisible()
  await page.getByRole('button', { name: 'Completar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Completar evaluación' }).click()
  await expect(page.getByText('Completada')).toBeVisible()

  // 4. Owner: start the decision, select the vendor, justify, assign an
  // approver, and request approval.
  await page.getByRole('link', { name: 'Decisión' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/decision`, wait)
  await page.getByRole('button', { name: 'Iniciar decisión' }).click()

  await page.getByLabel('Resultado').click()
  await page.getByRole('option', { name: 'Proveedor seleccionado' }).click()
  await page.getByLabel('Proveedor seleccionado').click()
  await page.getByRole('option', { name: 'Proveedor Uno (dev)' }).click()
  await page
    .getByLabel('Justificación')
    .fill('El proveedor cumple todos los requisitos obligatorios y su TCO es el menor.')
  await page.getByRole('button', { name: 'Guardar selección' }).click()
  await expect(page.getByRole('button', { name: 'Guardar selección' })).toBeEnabled()

  await page.getByLabel('Aprobador de la decisión').click()
  await page.getByRole('option', { name: 'Aprobador A' }).click()
  await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
  await expect(page.getByText('Aprobación pendiente')).toBeVisible()

  // 5. A non-assigned actor (an evaluator, not the decision's approver, not
  // the owner) can read the decision tab but must never see decide controls.
  await loginAsBuyer(page, 'evaluator.functional.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Decisión' }).click()
  await expect(page.getByText('Aprobación pendiente')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Aprobar' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Rechazar' })).toHaveCount(0)

  // 6. Approver rejects with a comment.
  await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Decisión' }).click()
  await page
    .getByLabel('Comentario (obligatorio para rechazar)')
    .fill('Falta evidencia de cumplimiento de un requisito.')
  await page.getByRole('button', { name: 'Rechazar' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Rechazar' }).click()
  await expect(page.getByText('Rechazada').first()).toBeVisible()

  // 7. Owner edits the justification and requests approval again - rejected
  // is not terminal (same shape as ApprovalStatus, plan section 10 decision 3).
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Decisión' }).click()
  await page
    .getByLabel('Justificación')
    .fill(
      'El proveedor cumple todos los requisitos obligatorios, su TCO es el menor y ya se aclaró la evidencia faltante.',
    )
  await page.getByRole('button', { name: 'Guardar selección' }).click()
  await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
  await expect(page.getByText('Aprobación pendiente')).toBeVisible()

  // 8. Approver approves - the memo de cierre is created and read-only.
  await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Decisión' }).click()
  await page.getByRole('button', { name: 'Aprobar' }).click()
  await expect(page.getByText('Aprobada').first()).toBeVisible()
  await expect(page.getByText('Memo de cierre')).toBeVisible()
  // Scoped to the memo's own summary line ("Resultado: ...") - "Proveedor
  // Uno (dev)" alone also appears in the results table above, which would
  // otherwise trip Playwright's strict-mode ambiguity check.
  await expect(page.getByText(/Resultado:.*Proveedor Uno \(dev\)/)).toBeVisible()
  await expect(page.getByText(/es de solo lectura/)).toBeVisible()

  await checkA11y(page)
})
