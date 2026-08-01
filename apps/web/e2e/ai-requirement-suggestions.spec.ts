import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

/** Same helper as knowledge-templates.spec.ts / evaluation-wizard.spec.ts. */
async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

/**
 * Fase 13 (ai, ADR 0021): proves the trigger request and the adaptive-
 * polling wiring (ADR 0012) work against the real running API - not a
 * mocked fetch, unlike the component test covering the full
 * trigger/succeeded/accept flow (AiSuggestRequirementsDialog.test.tsx).
 *
 * Scoping note: `make test-e2e` doesn't start a worker process or the
 * Service Bus emulator profile (`docker-compose.yml`'s `servicebus`
 * profile), and CI never configures real Azure OpenAI credentials - so a
 * job triggered here has nothing to process it and stays `queued`
 * indefinitely, by design. This spec verifies the trigger succeeds and the
 * UI enters its polling/loading state against the real server; the
 * succeeded -> review -> accept path is covered by the Vitest component
 * test instead, where the job status can be mocked deterministically.
 * Wiring a real worker + Service Bus emulator + a test-only deterministic
 * AI provider into the E2E environment is real future work, not something
 * to bolt onto `scripts/test-e2e.sh` (which has already caused one CI
 * segfault from process-orchestration complexity) without dedicated
 * verification of its own.
 */
test.describe('AI requirement suggestions (Fase 13)', () => {
  test('owner triggers a suggestion job and sees it start generating', async ({ page }) => {
    const evaluationName = `RFP con IA ${Date.now()}`

    await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
    await page.waitForURL('**/evaluations', wait)

    await page.getByRole('link', { name: 'Nueva evaluación' }).click()
    await page.waitForURL('**/evaluations/new', wait)
    await page.getByLabel('Nombre').fill(evaluationName)
    await page.getByRole('button', { name: 'Crear y continuar' }).click()
    await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

    await page.getByRole('button', { name: 'Sugerir con IA' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page
      .getByLabel('¿Qué necesitas comprar?')
      .fill('Necesitamos una plataforma de reportes con dashboards configurables')
    await page.getByRole('button', { name: 'Generar sugerencias' }).click()

    await expect(page.getByText('Generando sugerencias…')).toBeVisible()
    // The dialog must never show an error for a queued job with nothing
    // processing it yet - only a genuinely failed AIExecution should.
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})
