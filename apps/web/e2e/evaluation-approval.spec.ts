import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

/** Every navigation here is an in-app link click, never `page.goto`, once a
 * session is established - the buyer access token lives only in memory
 * (AUTH-PROD scope decision #2), and a real browser navigation reloads the
 * SPA from scratch, wiping it and bouncing back to /login. */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

async function openEvaluationApprovalTab(page: Page, name: string) {
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Aprobación' }).click()
}

async function createDraftEvaluation(page: Page, name: string): Promise<void> {
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(name)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

  const section = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Funcional', exact: true }) })
  await section.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req funcional')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('40')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('20')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Siguiente' }).click()

  await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toBeVisible()
  await page.getByRole('button', { name: 'Vincular' }).click()
  await expect(page.getByText('Proveedores vinculados (1 / 6)')).toBeVisible()
  await page.getByRole('button', { name: 'Siguiente' }).click()
}

/**
 * Fase 12 journeys not already covered by evaluation-wizard.spec.ts's happy
 * path: rejection forces a fresh approval cycle after any edit (the
 * soft-invalidation rule, plan §14/§32 Blocker 3), and a non-assigned actor
 * never sees decision controls. Cross-tenant isolation for the new routes
 * is covered at the backend (tests/security/test_tenant_isolation.py) -
 * this app's memory-only buyer JWT (AUTH-PROD scope decision #2) means a
 * real browser navigation to a raw URL always forces a fresh, unauthenticated
 * load, so it isn't a meaningful way to exercise cross-tenant access at the
 * UI layer.
 */
test.describe('evaluation approval and publication (Fase 12)', () => {
  test('approver rejects with a comment, owner edits, and must request approval again', async ({
    page,
  }) => {
    const name = `RFP Rechazo E2E ${Date.now()}`
    await createDraftEvaluation(page, name)

    await page.getByLabel('Aprobador').click()
    await page.getByRole('option', { name: 'Aprobador A' }).click()
    await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
    await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
    await openEvaluationApprovalTab(page, name)
    await page.getByLabel('Comentario (obligatorio para rechazar)').fill('Falta detalle técnico.')
    await page.getByRole('button', { name: 'Rechazar' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Rechazar' }).click()
    await expect(page.getByText('Rechazada').first()).toBeVisible()

    // Owner sees the rejection comment. Editing while "rejected" does NOT
    // reset approval_status further (it's already not-approved, staying
    // "rejected" until explicitly re-requested) - so no invalidation
    // notice is expected yet, only that the evaluation stays editable.
    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
    await page.getByRole('link', { name: 'Requerimientos' }).click()
    await page.getByRole('button', { name: 'Editar' }).first().click()
    await page.getByLabel('Título').fill('Req funcional (revisado)')
    await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
    await expect(page.getByText('Req funcional (revisado)')).toBeVisible()

    // Approval must be requestable again (not stuck "rejected" forever -
    // request_approval is valid from both not_requested and rejected).
    await page.getByRole('link', { name: 'Aprobación' }).click()
    await expect(page.getByRole('button', { name: 'Solicitar aprobación' })).toBeEnabled()
    await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    // Now editing while "pending" DOES reset approval_status server-side
    // (the soft-invalidation rule) and must surface an explicit, immediate
    // notice - not just a badge change discovered later.
    await page.getByRole('link', { name: 'Requerimientos' }).click()
    await page.getByRole('button', { name: 'Editar' }).first().click()
    await page.getByLabel('Título').fill('Req funcional (revisado de nuevo)')
    await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
    await expect(
      page.getByText('La solicitud de aprobación fue retirada porque se modificó la evaluación'),
    ).toBeVisible()
    await page.getByRole('link', { name: 'Aprobación' }).click()
    await expect(page.getByText('Sin solicitar')).toBeVisible()
  })

  test('a non-assigned actor never sees approve/reject controls', async ({ page }) => {
    const name = `RFP No Autorizado E2E ${Date.now()}`
    await createDraftEvaluation(page, name)

    await page.getByLabel('Aprobador').click()
    await page.getByRole('option', { name: 'Aprobador A' }).click()
    await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
    await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    // A functional evaluator (not the assigned approver, not the owner)
    // can read the approval tab but must never see a decision control.
    await loginAsBuyer(page, 'evaluator.functional.a@dev.procurawise.local')
    await openEvaluationApprovalTab(page, name)
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Aprobar' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Rechazar' })).toHaveCount(0)
  })
})
