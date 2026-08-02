import { test, expect, type Page } from '@playwright/test'

const wait = { waitUntil: 'commit' as const }
const DEV_BUYER_PASSWORD = 'dev-password-2026'

async function loginAsBuyer(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña').fill(DEV_BUYER_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), wait)
}

/**
 * Fase 15 backlog acceptance criterion, exercised end to end for real:
 * "Proveedor no accede al formulario de respuesta sin aceptar ambos
 * Agreement". Covers the one path e2e/vertical-slice.spec.ts deliberately
 * does not (it reuses the already-onboarded, already-agreements-accepted
 * seed vendor): a comprador onboarding a brand-new vendor organization from
 * scratch, the vendor redeeming the invitation link, and clearing the
 * Agreement gate before ever seeing a proposal.
 */
test('vendor onboarding: comprador crea un proveedor nuevo, el contacto acepta su invitación y ambos Agreement', async ({
  page,
}) => {
  const uniqueEmail = `e2e.vendor.${Date.now()}@dev.procurawise.local`

  // 1. Comprador: crea un proveedor nuevo + invita a su contacto principal,
  // usando la evaluación sembrada por seed-dev (ya en collecting_responses).
  await loginAsBuyer(page, 'owner.a@dev.procurawise.local')
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: 'Evaluacion de ejemplo (dev)' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(/\/vendors$/, wait)

  await page.getByLabel('Nombre del proveedor').fill('Proveedor E2E Nuevo')
  await page.getByLabel('Correo del contacto principal').fill(uniqueEmail)
  await page.getByLabel('Nombre del contacto principal').fill('Contacto E2E')
  await page.getByRole('button', { name: 'Crear proveedor e invitar' }).click()

  const inviteCode = page.locator('code')
  await expect(inviteCode).toBeVisible()
  const inviteUrl = await inviteCode.textContent()
  expect(inviteUrl).toBeTruthy()
  const token = new URL(inviteUrl!).searchParams.get('token')
  expect(token).toBeTruthy()

  // 2. Proveedor: acepta la invitación (crea su contraseña) - flujo público,
  // sin sesión previa.
  await page.goto(`/vendor/accept-invitation?token=${token}`)
  await page.getByLabel('Contraseña', { exact: true }).fill('e2e-vendor-password-123')
  await page.getByLabel('Confirma tu contraseña').fill('e2e-vendor-password-123')
  await page.getByRole('button', { name: 'Crear acceso' }).click()

  // 3. Gate de Agreements: no debe poder ver "Mis propuestas" todavía.
  await expect(
    page.getByRole('heading', { name: 'Antes de continuar, revisa y acepta estos documentos' }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Mis propuestas' })).toHaveCount(0)

  const ndaSection = page.getByText('Acuerdo de confidencialidad (NDA)').locator('..')
  await ndaSection.getByRole('checkbox').check()
  await ndaSection.getByRole('button', { name: 'Aceptar' }).click()

  // Todavía falta el segundo Agreement.
  await expect(page.getByRole('heading', { name: 'Mis propuestas' })).toHaveCount(0)

  const coiSection = page.getByText('Declaración de conflicto de interés').locator('..')
  await coiSection.getByRole('checkbox').check()
  await coiSection.getByRole('button', { name: 'Aceptar' }).click()

  // 4. Ambos Agreement aceptados: ahora sí llega al portal.
  await expect(page.getByRole('heading', { name: 'Mis propuestas' })).toBeVisible()
})
