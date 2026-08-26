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

/** The outer requirement card in VendorProposalDetailPage.tsx - located by
 * its heading rather than by requirement id (unknown to this test ahead of
 * time), disambiguated from ProposalDocumentsPanel's own identically
 * classed wrapper by requiring the heading inside it. */
function requirementCard(page: Page, title: string): Locator {
  return page.locator('div.rounded-md.border.border-border.p-4', {
    has: page.getByRole('heading', { name: title, exact: true }),
  })
}

async function createDraftEvaluation(page: Page, name: string): Promise<void> {
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(name)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

  const functionalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Funcional', exact: true }) })
  await functionalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req funcional evidencia')
  await page.getByLabel('Descripción', { exact: true }).fill('d')
  await page.getByLabel('Peso (%)').fill('100')
  await page.getByRole('button', { name: 'Guardar requerimiento' }).click()
  await expect(page.getByRole('button', { name: 'Guardar requerimiento' })).toHaveCount(0)

  const technicalSection = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Técnico', exact: true }) })
  await technicalSection.getByRole('button', { name: 'Agregar requerimiento' }).click()
  await page.getByLabel('Categoría').fill('Core')
  await page.getByLabel('Título').fill('Req técnico evidencia')
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
 * Fase 16 backlog acceptance criterion: "Archivo subido, versionado, URL
 * expira tras tiempo configurado" - exercised end to end against a real
 * Azurite blob (via `make test-e2e`'s Docker stack), not just mocked.
 * Builds its own draft evaluation (like evaluation-approval.spec.ts) rather
 * than reusing the shared seeded one, since this file runs alphabetically
 * before vertical-slice.spec.ts advances that seed to "completed" and this
 * spec needs its own proposal to stay in `draft` up to the submit step.
 */
test('documents: vendor uploads/reemplaza/descarga evidencia, comprador la revisa de solo lectura', async ({
  page,
}) => {
  const evaluationName = `RFP con evidencia E2E ${Date.now()}`

  // 1. Owner: draft evaluation with one vendor linked - createDraftEvaluation
  // leaves the page on the wizard's final "Review" step, which already has
  // the approval-request controls inline (same as evaluation-approval.spec.ts).
  await createDraftEvaluation(page, evaluationName)
  const evaluationId = page.url().split('/evaluations/')[1].split('/wizard')[0]

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

  // 2. Vendor: open the proposal, upload evidence for one requirement,
  // replace it with a second version, upload a general attachment, and try
  // (and fail) an obviously disallowed file type.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  const functionalCard = requirementCard(page, 'Req funcional evidencia')
  await functionalCard.getByRole('textbox').first().fill('Respuesta funcional')
  await functionalCard.getByRole('textbox').first().blur()
  const technicalCard = requirementCard(page, 'Req técnico evidencia')
  await technicalCard.getByRole('textbox').first().fill('Respuesta técnica')
  await technicalCard.getByRole('textbox').first().blur()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()

  await functionalCard.getByRole('button', { name: 'Adjuntar evidencia' }).click()
  await functionalCard.locator('input[type="file"]').setInputFiles({
    name: 'evidencia-v1.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 evidencia version 1'),
  })
  await expect(functionalCard.getByText('evidencia-v1.pdf')).toBeVisible()
  await expect(functionalCard.getByText('· v1')).toBeVisible()

  // Replace: same requirement slot, new version - the old filename
  // disappears, "v2" appears, nothing is duplicated.
  await functionalCard.getByRole('button', { name: 'Reemplazar evidencia' }).click()
  await functionalCard.locator('input[type="file"]').setInputFiles({
    name: 'evidencia-v2.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 evidencia version 2'),
  })
  await expect(functionalCard.getByText('evidencia-v2.pdf')).toBeVisible()
  await expect(functionalCard.getByText('· v2')).toBeVisible()
  await expect(functionalCard.getByText('evidencia-v1.pdf')).toHaveCount(0)

  const documentsPanel = page
    .locator('div.rounded-md.border.border-border.p-4')
    .filter({ has: page.getByRole('heading', { name: 'Documentos adjuntos' }) })
  await documentsPanel.getByRole('button', { name: 'Adjuntar documento' }).click()
  await documentsPanel.locator('input[type="file"]').setInputFiles({
    name: 'brochure-general.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 adjunto general'),
  })
  await expect(documentsPanel.getByText('brochure-general.pdf')).toBeVisible()

  await documentsPanel.getByRole('button', { name: 'Adjuntar documento' }).click()
  await documentsPanel.locator('input[type="file"]').setInputFiles({
    name: 'script.exe',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('MZ contenido no permitido'),
  })
  await expect(page.getByText('Revisa los campos marcados antes de continuar.')).toBeVisible()
  await expect(documentsPanel.getByText('script.exe')).toHaveCount(0)

  // 3. Download the just-uploaded evidence - a real, freshly authorized SAS
  // URL against Azurite, not a mock.
  const [download] = await Promise.all([
    page.context().waitForEvent('download'),
    functionalCard.getByRole('button', { name: 'Descargar' }).click(),
  ])
  expect(download.suggestedFilename()).toBe('evidencia-v2.pdf')

  // 4. Submit - evidence uploaded so far freezes into the snapshot; no more
  // upload/replace/delete afterward.
  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Esta propuesta ya fue enviada y no puede editarse.')).toBeVisible()

  await expect(functionalCard.getByText('evidencia-v2.pdf')).toBeVisible()
  await expect(functionalCard.getByRole('button', { name: 'Reemplazar evidencia' })).toHaveCount(0)
  await expect(functionalCard.getByRole('button', { name: 'Eliminar' })).toHaveCount(0)
  await expect(documentsPanel.getByRole('button', { name: 'Adjuntar documento' })).toHaveCount(0)

  // 5. Owner: start the evaluation and review the same evidence read-only
  // from the buyer side (BuyerDocumentsList on ScoringPage).
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  await page.getByRole('link', { name: 'Calificar' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/score$/, wait)

  await expect(page.getByRole('heading', { name: 'Documentos del proveedor' })).toBeVisible()
  await expect(page.getByText('evidencia-v2.pdf')).toBeVisible()
  await expect(page.getByText('brochure-general.pdf')).toBeVisible()
  // Read-only: the buyer router has no upload/delete endpoints at all.
  await expect(page.getByRole('button', { name: 'Eliminar' })).toHaveCount(0)
  await expect(page.locator('input[type="file"]')).toHaveCount(0)

  const [buyerDownload] = await Promise.all([
    page.context().waitForEvent('download'),
    page
      .locator('li')
      .filter({ hasText: 'evidencia-v2.pdf' })
      .getByRole('button', { name: 'Descargar' })
      .click(),
  ])
  expect(buyerDownload.suggestedFilename()).toBe('evidencia-v2.pdf')

  await checkA11y(page)
})
