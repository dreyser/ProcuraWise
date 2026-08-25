import { test, expect, type Page } from '@playwright/test'

import { assertKeyboardFocusStaysVisible, checkA11y } from './support/a11y'

const wait = { waitUntil: 'commit' as const }

const DEV_BUYER_PASSWORD = 'dev-password-2026'
const DEV_VENDOR_PASSWORD = 'dev-vendor-password-2026'

/**
 * Buyer identity (evaluation_owner/evaluator_functional) is real auth after AUTH-PROD -
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
 * Fase 15: vendor_contact now authenticates via a real login too
 * (token_use=vendor_access), same in-memory-only, no-persistence discipline
 * as the buyer login above - a completely separate mechanism/credential,
 * not just a different role on the same session.
 */
async function loginAsVendor(page: Page, email: string) {
  await page.goto('/vendor/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_VENDOR_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/vendor/login'), wait)
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

  // 1b. Internal approval (Fase 12) - start-collection now requires
  // approval_status === "approved". This seeded evaluation starts
  // "not_requested" (dev_seed.py leaves it that way on purpose), so the
  // owner requests approval and the assigned approver decides before
  // publication can proceed. Every navigation below is an in-app link
  // click, never `page.goto` - the buyer access token lives only in memory
  // (AUTH-PROD scope decision #2), and a real browser navigation reloads
  // the SPA from scratch, wiping it and bouncing back to /login.
  await page.getByRole('link', { name: 'Aprobación' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/approval`, wait)
  await page.getByLabel('Aprobador').click()
  await page.getByRole('option', { name: 'Aprobador A' }).click()
  await page.getByLabel('Fecha límite de respuesta').fill('2030-01-01')
  await page.getByRole('button', { name: 'Solicitar aprobación' }).click()
  await expect(page.getByText('Aprobación pendiente')).toBeVisible()
  // Fase 26 (Hardening, plan Bloque 5): this spec covers both journeys the
  // founder named as needing deeper WCAG 2.1 AA coverage - buyer owner
  // end-to-end (this checkpoint on) and vendor answering a proposal
  // (checked further below) - checked at multiple points along the flow,
  // not just once at the very end.
  await checkA11y(page)

  await loginAsBuyer(page, 'approver.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Aprobación' }).click()
  await page.getByRole('button', { name: 'Aprobar' }).click()
  await expect(page.getByText('Aprobada')).toBeVisible()

  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}`, wait)
  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/vendors`, wait)
  await page.getByRole('button', { name: 'Iniciar recepción de propuestas' }).click()
  await page.getByRole('button', { name: 'Iniciar recepción' }).click()
  await expect(page.getByText('Recibiendo propuestas')).toBeVisible()

  // 2. Vendor: answer both required requirements and submit. Agreements
  // (NDA + conflict of interest) are already accepted for this seeded
  // contact (dev_seed.py) - the fresh-invitation acceptance flow is covered
  // separately by e2e/vendor-onboarding.spec.ts.
  await loginAsVendor(page, 'vendor.a@dev.procurawise.local')
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
  // Vendor journey checkpoint - both automated axe rules and a keyboard
  // traversal smoke check (no manual tester/screen reader is available in
  // this environment, this is the closest automatable proxy).
  await checkA11y(page)
  await assertKeyboardFocusStaysVisible(page)

  // Fase 20: a nonzero cost item is required for the economic component's
  // TCO-normalized 70% to be "available" rather than "no_comparable" - MXN
  // matches the evaluation's default base_currency, so no FXRate needs to
  // exist (same reasoning as tco.spec.ts).
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

  // 3. Owner: start evaluation. Fresh login - the previous owner session (if
  // any survived step 1) was already wiped by loginAsVendor's `page.goto`.
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
  // owner_a - not just a role switch, a genuinely different login. No
  // Assignment exists for this seeded evaluation, so evaluator_functional
  // may still score its technical requirement too (Fase 9 Block 3's
  // backward-compatible "unassigned section" rule).
  await loginAsBuyer(page, 'evaluator.functional.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('link', { name: 'Calificar' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/score$/, wait)
  await expect(page.getByText('Calificados: 0 / 2')).toBeVisible()
  await checkA11y(page)

  // The 0-5 radios are visually sr-only (the styled <label> is the
  // clickable surface, a legitimate accessible pattern) - force the click
  // since Playwright's actionability check won't click "through" the label.
  //
  // UAT-15 (R3): scoring autosaves - checking a score radio is itself the
  // save trigger now, there is no separate "Guardar calificación" button to
  // click afterward. Checked one at a time (not all-then-assert) so each
  // "Calificados: N / 2" increment is verified against the specific write
  // that caused it, same proof the old check-all/save-all/assert-all loop
  // gave before autosave removed the middle step.
  // exact: true matters here - Playwright's default name matcher is a
  // substring match, and EconomicAssessmentPanel's criterion radios carry
  // aria-labels like "Pago y plazo: 5", which also contain "5" and would
  // otherwise be counted alongside the real functional/technical inputs.
  const scoreButtons5 = page.getByRole('radio', { name: '5', exact: true })
  const scoreCount = await scoreButtons5.count()
  for (let i = 0; i < scoreCount; i += 1) {
    await scoreButtons5.nth(i).check({ force: true })
    await expect(page.getByText(`Calificados: ${i + 1} / 2`)).toBeVisible()
  }

  // 4b. Fase 20: the economic assessment (commercial/risk, score 3 - not an
  // extreme value, so no comment is required). UAT-16 remediación (R1B,
  // Decisión F): evaluator_functional/technical never see this section at
  // all now, regardless of Assignment - a genuinely different login as
  // evaluator_economic is required here, same "different buyer account,
  // not just a role switch" principle as every other actor change in this
  // spec.
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await page.waitForURL('**/login**', wait)
  await loginAsBuyer(page, 'evaluator.economic.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Propuestas' }).click()
  await page.waitForURL(`**/evaluations/${evaluationId}/proposals`, wait)
  await page.getByRole('link', { name: 'Calificar' }).click()
  await page.waitForURL(/\/proposals\/[a-f0-9]+\/score$/, wait)

  const economicCriterionLabels = [
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
  for (const label of economicCriterionLabels) {
    await page.getByRole('radio', { name: `${label}: 3` }).check({ force: true })
  }
  await page.getByRole('button', { name: 'Guardar evaluación económica' }).click()
  await expect(page.getByRole('button', { name: 'Guardar evaluación económica' })).toBeEnabled()
  await expect(page.getByRole('alert')).toHaveCount(0)

  // 5. Owner: consult results and complete. Uses the "Cerrar sesión" button
  // again here (rather than another bare page.goto) to also exercise that
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
  // Economic: TCO_pct=100 (the only submitted proposal), commercial_pct=
  // risk_pct=60 (all 10 criteria scored 3/5) -> 40 x (0.70x1 + 0.15x0.6 +
  // 0.15x0.6) = 35.2 / 40. Final: 40 + 20 + 35.2 = 95.2 / 100.
  await expect(page.getByText('35.2 / 40')).toBeVisible()
  await expect(page.getByText('95.2 / 100')).toBeVisible()
  await expect(page.getByText(/No constituye recomendacion de adjudicacion/)).toBeVisible()
  // Owner journey final checkpoint - results page.
  await checkA11y(page)
  await assertKeyboardFocusStaysVisible(page)

  await page.getByRole('button', { name: 'Completar evaluación' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Completar evaluación' }).click()
  await expect(page.getByText('Completada')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Completar evaluación' })).toHaveCount(0)
})
