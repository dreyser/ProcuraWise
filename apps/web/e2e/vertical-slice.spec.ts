import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }

async function selectActor(page: Page, namePattern: RegExp) {
  await page.getByRole('button', { name: 'Cambiar de actor' }).click()
  await page.waitForURL('**/dev/select-actor**', wait)
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
 */
test('vertical slice: owner -> vendor -> evaluator -> owner, end to end', async ({ page }) => {
  // 1. Owner: start collection.
  await page.goto('/')
  await page.waitForURL('**/dev/select-actor**', wait)
  await page.getByRole('button', { name: /Owner A/ }).click()
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  const evaluationId = page.url().split('/evaluations/')[1]

  await page.goto(`/evaluations/${evaluationId}/vendors`)
  await page.getByRole('button', { name: 'Iniciar recepción de propuestas' }).click()
  await page.getByRole('button', { name: 'Iniciar recepción' }).click()
  await expect(page.getByText('Recibiendo propuestas')).toBeVisible()

  // 2. Vendor: answer both required requirements and submit.
  await selectActor(page, /Vendor Contact A/)
  await page.goto('/vendor/proposals')
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

  // 3. Owner: start evaluation.
  await selectActor(page, /Owner A/)
  await page.goto(`/evaluations/${evaluationId}/proposals`)
  await page.getByRole('button', { name: 'Iniciar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Iniciar evaluación' }).click()
  await expect(page.getByText('En evaluación')).toBeVisible()

  // 4. Evaluator: score both requirements.
  await selectActor(page, /Evaluator A/)
  await page.goto(`/evaluations/${evaluationId}/proposals`)
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

  // 5. Owner: consult results and complete.
  await selectActor(page, /Owner A/)
  await page.goto(`/evaluations/${evaluationId}/results`)

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
