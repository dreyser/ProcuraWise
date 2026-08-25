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

async function loginAsVendor(page: Page, email: string, password = DEV_VENDOR_PASSWORD) {
  await page.goto('/vendor/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/vendor/login'), wait)
}

/** The outer requirement card in VendorProposalDetailPage.tsx - same
 * disambiguation approach as documents.spec.ts, since RequirementEvidenceUpload
 * and RequirementQuestionThread are both mounted inside it. */
function requirementCard(page: Page, title: string): Locator {
  return page.locator('div.rounded-md.border.border-border.p-4', {
    has: page.getByRole('heading', { name: title, exact: true }),
  })
}

interface DraftEvaluation {
  evaluationId: string
  vendorBEmail: string
}

const VENDOR_B_PASSWORD = 'e2e-vendor-qna-password-123'

/**
 * Builds a draft evaluation with both requirement dimensions complete
 * (hasCompleteWeights gates the wizard's "Siguiente"), links vendor A from
 * the catalog, and onboards a brand-new vendor B via "Dar de alta un
 * proveedor nuevo" - all while the evaluation is still `draft`. Both vendor
 * links must happen here, before "Solicitar aprobación": VendorsPage only
 * renders its linking/invite sections while `canEdit` (`status === 'draft'`),
 * and EvaluationService.reserve_vendor_slot applies
 * approval_invalidation_extra_set() on every new link, which would reset an
 * already-pending/approved request back to `not_requested`.
 *
 * Every authenticated-route transition below uses a real link/button click,
 * never `page.goto` - AuthContext.tsx keeps the buyer/vendor session in
 * memory only (no persisted token), so a hard navigation silently bounces
 * back to /login instead of reaching the intended page.
 */
async function createDraftEvaluationWithTwoVendors(
  page: Page,
  name: string,
): Promise<DraftEvaluation> {
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(name)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1].split('/wizard')[0]

  // hasCompleteWeights (evaluationReadiness.ts) gates "Siguiente" on both the
  // functional (40) and technical (20) dimensions reaching their exact
  // target - same two requirements documents.spec.ts adds, even though this
  // spec only interacts with the functional one.
  const functionalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Funcional', exact: true }) })
  await functionalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req funcional Q&A')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('40')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico Q&A')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso').fill('20')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Siguiente' }).click()

  await expect(page.getByRole('heading', { name: 'Vincular proveedor' })).toBeVisible()
  await page.getByRole('button', { name: 'Vincular' }).click()
  await expect(page.getByText(/Proveedores vinculados \(1 \/ \d+\)/)).toBeVisible()

  // Onboard vendor B now, still in draft, via the real VendorsPage route
  // (the wizard's own vendor step only has the catalog picker, not the
  // "create new vendor" form) - reached via AppShell's persistent
  // "Evaluaciones" nav link, since the wizard has no tab bar of its own.
  await page.getByRole('link', { name: 'Evaluaciones' }).click()
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/vendors`, wait)

  const vendorBEmail = `e2e.vendor.qna.${Date.now()}@dev.procurawise.local`
  await page.getByLabel('Nombre del proveedor').fill('Proveedor E2E QnA')
  await page.getByLabel('Correo del contacto principal').fill(vendorBEmail)
  await page.getByLabel('Nombre del contacto principal').fill('Contacto E2E QnA')
  await page.getByRole('button', { name: 'Crear proveedor e invitar' }).click()

  const inviteCode = page.locator('code')
  await expect(inviteCode).toBeVisible()
  const inviteUrl = await inviteCode.textContent()
  const token = new URL(inviteUrl!).searchParams.get('token')
  expect(token).toBeTruthy()

  // Vendor B redeems the invitation and accepts both Agreements right away,
  // so it only needs a plain login later in the test. This is a public,
  // unauthenticated route, so a hard `page.goto` is fine here - there is no
  // buyer session left to lose.
  await page.goto(`/vendor/accept-invitation?token=${token}`)
  await page.getByLabel('Contraseña', { exact: true }).fill(VENDOR_B_PASSWORD)
  await page.getByLabel('Confirma tu contraseña').fill(VENDOR_B_PASSWORD)
  await page.getByRole('button', { name: 'Crear acceso' }).click()
  const ndaSection = page.getByText('Acuerdo de confidencialidad (NDA)').locator('..')
  await ndaSection.getByRole('checkbox').check()
  await ndaSection.getByRole('button', { name: 'Aceptar' }).click()
  const coiSection = page.getByText('Declaración de conflicto de interés').locator('..')
  await coiSection.getByRole('checkbox').check()
  await coiSection.getByRole('button', { name: 'Aceptar' }).click()
  await expect(page.getByRole('heading', { name: 'Mis propuestas' })).toBeVisible()

  // Resume the wizard as owner via "Continuar configuración" - deriveWizardStep.ts
  // jumps straight to the review step since weights and vendor links are
  // already complete.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  const row = page.locator('tr').filter({ hasText: name })
  await row.getByRole('link', { name: 'Continuar configuración' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)
  await expect(page.getByLabel('Aprobador')).toBeVisible()

  return { evaluationId, vendorBEmail }
}

/**
 * Fase 17 backlog acceptance criterion: "Pregunta de proveedor visible a
 * comprador; respuesta publicada según visibilidad configurada" - exercised
 * end to end with two real vendor organizations, confirming both that a
 * private answer never reaches a second vendor and that a published answer
 * never reveals which vendor asked it (brief §6.6/§26, plan §8.1).
 */
test('qna: proveedor pregunta, comprador responde con visibilidad, y un segundo proveedor solo ve lo publicado sin identidad', async ({
  page,
}) => {
  const evaluationName = `RFP con Q&A E2E ${Date.now()}`

  // 1. Owner: draft evaluation with one requirement, vendor A linked from
  // the catalog, and vendor B onboarded fresh (both while still draft) -
  // then approved and moved to collecting_responses.
  const { evaluationId, vendorBEmail } = await createDraftEvaluationWithTwoVendors(
    page,
    evaluationName,
  )

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

  // 2. Vendor A: ask a requirement-scoped question and a general question,
  // plus a third question that gets withdrawn right away.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  const requirementThread = requirementCard(page, 'Req funcional Q&A')
  await requirementThread
    .getByPlaceholder('Pregunta sobre este requerimiento…')
    .fill('¿Soportan SSO?')
  await requirementThread.getByRole('button', { name: 'Preguntar' }).click()
  await expect(requirementThread.getByText('¿Soportan SSO?')).toBeVisible()

  const generalPanel = page
    .locator('div.rounded-md.border.border-border.p-4')
    .filter({ has: page.getByRole('heading', { name: 'Preguntas generales' }) })

  await generalPanel.getByPlaceholder('Escribe tu pregunta…').fill('Pregunta a retirar')
  await generalPanel.getByRole('button', { name: 'Preguntar' }).click()
  await expect(generalPanel.getByText('Pregunta a retirar')).toBeVisible()
  await generalPanel.getByRole('button', { name: 'Retirar' }).click()
  await expect(generalPanel.getByText('Pregunta a retirar')).toHaveCount(0)

  await generalPanel.getByPlaceholder('Escribe tu pregunta…').fill('¿Cuándo cierra el RFP?')
  await generalPanel.getByRole('button', { name: 'Preguntar' }).click()
  await expect(generalPanel.getByText('¿Cuándo cierra el RFP?')).toBeVisible()

  // 3. Owner: answer both questions from the Q&A tab - the requirement one
  // published anonymized, the general one kept private.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Q&A' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/qna`, wait)

  // Fase 28 remediación R1A (UAT-01): Q&A used to drop the evaluation nav
  // shell entirely - confirm the header/tab bar survived and the owner can
  // still navigate to another tab without using the browser back button.
  await expect(page.getByRole('heading', { name: evaluationName })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Requerimientos' })).toBeVisible()
  await page.getByRole('link', { name: 'Requerimientos' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/requirements`, wait)
  await page.getByRole('link', { name: 'Q&A' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/qna`, wait)

  await expect(page.getByText('Sin responder: 2 / 2')).toBeVisible()

  const ssoRow = page.locator('li').filter({ hasText: '¿Soportan SSO?' })
  await ssoRow.getByPlaceholder('Escribe la respuesta…').fill('Sí, soportamos SSO vía SAML.')
  await ssoRow.getByLabel('Publicada (anónima)').check()
  await ssoRow.getByRole('button', { name: 'Publicar respuesta' }).click()
  await expect(ssoRow.getByText('Sí, soportamos SSO vía SAML.')).toBeVisible()

  const closingRow = page.locator('li').filter({ hasText: '¿Cuándo cierra el RFP?' })
  await closingRow.getByPlaceholder('Escribe la respuesta…').fill('Cierra el 30 de agosto.')
  // "Privada" is already the default selection - no need to click it.
  await closingRow.getByRole('button', { name: 'Publicar respuesta' }).click()
  await expect(closingRow.getByText('Cierra el 30 de agosto.')).toBeVisible()

  await expect(page.getByText('Sin responder: 0 / 2')).toBeVisible()

  // 4. Vendor A: sees both of its own answers, with the visibility the owner
  // chose for each.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  await expect(requirementThread.getByText('Sí, soportamos SSO vía SAML.')).toBeVisible()
  await expect(requirementThread.getByText('Publicada (anónima)')).toBeVisible()
  await expect(generalPanel.getByText('Cierra el 30 de agosto.')).toBeVisible()
  await expect(generalPanel.getByText('Privada')).toBeVisible()

  // 5. Vendor B (onboarded earlier, still in draft, by the setup helper):
  // plain login now that the evaluation is collecting_responses, then open
  // its own proposal on the same evaluation.
  await loginAsVendor(page, vendorBEmail, VENDOR_B_PASSWORD)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  // 6. Vendor B sees the published, anonymized SSO question+answer, but
  // never the private one, and nothing that identifies vendor A.
  const publicBoard = page
    .locator('div.rounded-md.border.border-border.p-4')
    .filter({ has: page.getByRole('heading', { name: 'Preguntas públicas de otros proveedores' }) })
  await expect(publicBoard.getByText('¿Soportan SSO?')).toBeVisible()
  await expect(publicBoard.getByText('Sí, soportamos SSO vía SAML.')).toBeVisible()

  await expect(page.getByText('¿Cuándo cierra el RFP?')).toHaveCount(0)
  await expect(page.getByText('Cierra el 30 de agosto.')).toHaveCount(0)
  await expect(page.getByText('Proveedor Uno (dev)')).toHaveCount(0)

  await checkA11y(page)
})
