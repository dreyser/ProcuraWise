import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }

const DEV_BUYER_PASSWORD = 'dev-password-2026'

/**
 * Buyer identity (evaluation_owner/evaluator) is real auth after AUTH-PROD -
 * logs in via email+password against dev_seed.py's known dev password. The
 * access token lives only in memory (scope decision #2, no persistence), so
 * `page.goto()` - a real browser navigation, unlike a client-side <Link>
 * click - always requires a fresh login afterward; this helper always starts
 * from a clean /login visit rather than assuming any prior session survived.
 */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

/**
 * vendor_contact stays on the interim dev-header mechanism until Fase 15
 * (AUTH-PROD scope decision #1) - a completely separate mechanism from the
 * buyer login above, persisted via sessionStorage (survives the `page.goto`
 * below, unlike the buyer's in-memory access token).
 */
async function selectVendorActor(page: Page, namePattern: RegExp) {
  await page.goto('/dev/select-actor')
  await page.getByRole('button', { name: namePattern }).click()
  await page.waitForURL((url) => !url.pathname.includes('/dev/select-actor'), wait)
}

/**
 * The single, reproducible happy-path spec required by the backlog's VS-2C
 * acceptance criteria: owner prepares -> vendor answers and submits -> owner
 * starts evaluation -> evaluator scores -> owner reviews results and
 * completes. Runs against the seeded evaluation from `make seed-dev`
 * ("Evaluacion de ejemplo (dev)": functional=40 + technical=20, one vendor
 * already linked) so the spec doesn't also have to build fixtures.
 *
 * Every switch between actors here is a full login (owner/evaluator are
 * different real accounts; vendor is a different mechanism entirely) - no
 * step assumes a previous buyer session survived a `page.goto`, since it
 * deliberately doesn't (AUTH-PROD scope decision #2).
 */
test('vertical slice: owner -> vendor -> evaluator -> owner, end to end', async ({ page }) => {
  // 1. Owner: start collection.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1]

  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/vendors`, wait)
  await page.getByRole('button', { name: 'Iniciar recepción de propuestas' }).click()
  await page.getByRole('button', { name: 'Iniciar recepción' }).click()
  await expect(page.getByText('Recibiendo propuestas')).toBeVisible()

  // 2. Vendor: answer both required requirements and submit.
  await selectVendorActor(page, /Vendor Contact A/)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/vendor\/proposals\/[a-f0-9]+$/, wait)

  await page.getByRole('heading', { name: 'Gestion de flujos de aprobacion' }).waitFor()
  await page
    .getByRole('group', { name: 'Gestion de flujos de aprobacion' })
    .getByLabel('Cumple', { exact: true })
    .check()
  await page
    .getByRole('group', { name: 'API REST documentada' })
    .getByLabel('Cumple parcialmente', { exact: true })
    .check()
  await expect(page.getByText('Respondidos: 2 / 2')).toBeVisible()

  await page.getByRole('button', { name: 'Enviar propuesta' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Enviar propuesta' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Esta propuesta ya fue enviada y no puede editarse.')).toBeVisible()

  // 3. Owner: start evaluation. Fresh login - the previous owner session (if
  // any survived step 1) was already wiped by selectVendorActor's `page.goto`.
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  // 4. Evaluator: score both requirements. A different buyer account than
  // owner_a - not just a role switch, a genuinely different login.
  await loginAsBuyer(page, 'evaluator.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('link', { name: 'Calificar' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/score$/, wait)
  await expect(page.getByText('Calificados: 0 / 2')).toBeVisible()

  // The 0-5 radios are visually sr-only (the styled <label> is the
  // clickable surface, a legitimate accessible pattern) - force the click
  // since Playwright's actionability check won't click "through" the label.
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

  // 5. Owner: consult results and complete. Uses the "Cerrar sesión" button
  // once here (rather than another bare page.goto) to also exercise that
  // real UI action, not just the login form.
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await page.waitForURL('**/login**', wait)
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Resultados' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/results`, wait)

  await expect(page.getByText('Estado de calificación: Calificación completa')).toBeVisible()
  await expect(page.getByText('40 / 40')).toBeVisible()
  await expect(page.getByText('20 / 20')).toBeVisible()
  await expect(page.getByText('No disponible')).toBeVisible()
  await expect(page.getByText(/No constituye recomendacion de adjudicacion/)).toBeVisible()

  await page.getByRole('button', { name: 'Completar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Completar evaluación' }).click()
  await expect(page.getByText('Completada')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Completar evaluación' })).toHaveCount(0)
})
