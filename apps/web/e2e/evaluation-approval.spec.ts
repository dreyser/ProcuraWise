import { test, expect, type Page } from '@playwright/test'

import { checkA11y } from './support/a11y'

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
  await page.getByLabel('Peso (%)').fill('100')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso (%)').fill('100')
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

  test('a non-assigned actor never sees the Aprobación tab at all (UAT-08, ADR 0026)', async ({
    page,
  }) => {
    const name = `RFP No Autorizado E2E ${Date.now()}`
    await createDraftEvaluation(page, name)

    await page.getByLabel('Aprobador').click()
    await page.getByRole('option', { name: 'Aprobador A' }).click()
    await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
    await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    // A functional evaluator (not the assigned approver, not the owner, not
    // a reviewer) never sees a decision control - and, since UAT-08/ADR
    // 0026, doesn't even see the "Aprobación" tab in the nav, rather than
    // reaching a page with the status visible but no buttons.
    await loginAsBuyer(page, 'evaluator.functional.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)
    await page.getByRole('link', { name }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
    await expect(page.getByRole('link', { name: 'Requerimientos' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Aprobación' })).toHaveCount(0)

    await checkA11y(page)
  })

  test('R2 (ADR 0026): reviewer approves and auto-chains into pending approver, who then approves', async ({
    page,
  }) => {
    // The wizard's own step 4 (WizardStepReview.tsx) only ever offered the
    // plain owner->approver flow and stays that way after ADR 0026 (the
    // review stage is opt-in, reached from the standalone "Aprobación" tab,
    // never forced into the wizard's fast path) - so this journey leaves
    // the wizard after linking the vendor and does the review+approval
    // configuration from the dedicated page instead, exactly like an owner
    // who opts into a reviewer after finishing the wizard would.
    const name = `RFP Reviewer E2E ${Date.now()}`
    await createDraftEvaluation(page, name)
    await page.getByRole('link', { name: 'Evaluaciones' }).click()
    await openEvaluationApprovalTab(page, name)

    // Configure the reviewer AND the approver/deadline before requesting
    // review, not after - editing response_deadline (update_evaluation)
    // while review_status is "pending" deliberately invalidates that
    // pending review too (Evaluation.approval_invalidation_extra_set, ADR
    // 0026: an edit after a decision must invalidate it, same rule already
    // applied to the approver's own decision). Configuring everything
    // upfront, then kicking off review, is the real intended flow - and is
    // also what makes the auto-chain meaningful (approver+deadline already
    // valid by the time review is approved).
    await page.getByLabel('Revisor').click()
    await page.getByRole('option', { name: 'Colaborador Interno A' }).click()
    await page.getByLabel('Aprobador').click()
    await page.getByRole('option', { name: 'Aprobador A' }).click()
    await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
    await page.keyboard.press('Tab') // blur the deadline input, forcing its persist

    await page.getByRole('button', { name: 'Solicitar revisión' }).click()
    await expect(page.getByText('Revisión (opcional)')).toBeVisible()
    await expect(page.getByText('Revisión pendiente')).toBeVisible()
    // Now that a reviewer is actually assigned and pending, the review gate
    // in _approval_readiness_reasons blocks "Solicitar aprobación" even
    // though approver+deadline are already valid - review must pass first.
    await expect(page.getByRole('button', { name: 'Solicitar aprobación' })).toBeDisabled()

    await loginAsBuyer(page, 'collaborator.a@dev.procurawise.local')
    await openEvaluationApprovalTab(page, name)
    await expect(page.getByText('Tu revisión')).toBeVisible()
    await page.getByLabel('Comentario (obligatorio para rechazar)').first().fill('se ve bien')
    await page.getByRole('button', { name: 'Aprobar revisión' }).click()
    await expect(page.getByText('Aprobada').first()).toBeVisible()
    // Auto-chain (ADR 0026, blocking question #2): approval is already
    // pending without the owner requesting it a second time.
    await expect(page.getByText('Aprobación pendiente')).toBeVisible()

    await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
    await openEvaluationApprovalTab(page, name)
    await expect(page.getByText('Tu decisión')).toBeVisible()
    await page.getByRole('button', { name: 'Aprobar' }).click()
    await expect(page.getByText('Aprobada').first()).toBeVisible()

    // Acceptance criterion: reviewer never approves via the approver's own
    // control (already structurally true here - the reviewer's login never
    // saw an "Aprobar"/"Rechazar" pair under "Tu decisión", only "Tu
    // revisión" with "Aprobar revisión"/reject, a visibly distinct control).
  })
})
