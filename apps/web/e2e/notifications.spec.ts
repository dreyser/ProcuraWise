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

// owner.b (unlike owner.a, used by every other spec) holds two Memberships
// in the same tenant (evaluation_owner + approver, dev_seed.py) - login
// lands on the workspace picker instead of going straight to /evaluations.
async function selectEvaluationOwnerWorkspace(page: Page) {
  await page.getByRole('button', { name: /Responsable de evaluación/ }).click()
  await page.waitForURL('**/evaluations', wait)
}

/**
 * Fase 24 backlog acceptance criterion: "Notificación real enviada en al
 * menos un evento clave (invitación, publicación)". Mirrors
 * vendor-onboarding.spec.ts's invite step, then proves the resulting
 * Notification is actually visible in the vendor's in-app bell - real
 * email delivery itself is verified in integration
 * (test_notification_service.py, against LoggingNotificationEmailProvider),
 * not here, same established limitation already documented for AI/report
 * job specs (this file only exercises the in-app half of "Correo + centro").
 *
 * Deliberately runs against tenant B ("Globex Compradora (dev)", owner.b)
 * instead of the shared tenant A seed data every other vendor-creating spec
 * (qna.spec.ts, vendor-onboarding.spec.ts) already exercises: a newly
 * created VendorOrganization is tenant-wide, not scoped to one evaluation
 * (GET /vendor-organizations lists every unlinked org in the tenant), so
 * creating one in tenant A would leak into other specs' own "Vincular
 * proveedor" pickers depending on run order. Tenant B has no pre-seeded
 * evaluation, so this spec creates its own throwaway one via the wizard's
 * first step only, then reaches the standalone VendorsPage the same way
 * evaluation-wizard.spec.ts's own list does (Link by name, not the wizard's
 * own step 3, which only links existing catalog vendors - creating a new
 * one is only exposed on VendorsPage's "Crear proveedor e invitar" form).
 */
test('vendor invitation produces a visible, markable-as-read in-app notification for the invited contact', async ({
  page,
}) => {
  const uniqueSuffix = Date.now()
  const evaluationName = `RFP Notificaciones E2E ${uniqueSuffix}`
  const uniqueEmail = `e2e.notifications.${uniqueSuffix}@dev.procurawise.local`

  await loginAsBuyer(page, 'owner.b@dev.procurawise.local')
  await selectEvaluationOwnerWorkspace(page)
  await page.getByRole('link', { name: 'Nueva evaluación' }).click()
  await page.waitForURL('**/evaluations/new', wait)
  await page.getByLabel('Nombre').fill(evaluationName)
  await page.getByRole('button', { name: 'Crear y continuar' }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+\/wizard$/, wait)

  await page.getByRole('link', { name: 'Evaluaciones' }).click()
  await page.waitForURL('**/evaluations', wait)
  await page.getByRole('link', { name: evaluationName }).click()
  await page.waitForURL(/\/evaluations\/[a-f0-9]+$/, wait)
  await page.getByRole('link', { name: 'Proveedores' }).click()
  await page.waitForURL(/\/vendors$/, wait)

  // 1. Comprador: crea un proveedor nuevo + invita a su contacto principal.
  await page.getByLabel('Nombre del proveedor').fill('Proveedor E2E Notificaciones')
  await page.getByLabel('Correo del contacto principal').fill(uniqueEmail)
  await page.getByLabel('Nombre del contacto principal').fill('Contacto E2E Notificaciones')
  await page.getByRole('button', { name: 'Crear proveedor e invitar' }).click()

  const inviteCode = page.locator('code')
  await expect(inviteCode).toBeVisible()
  const inviteUrl = await inviteCode.textContent()
  const token = new URL(inviteUrl!).searchParams.get('token')
  expect(token).toBeTruthy()

  // 2. Proveedor: acepta la invitación (crea su contraseña).
  await page.goto(`/vendor/accept-invitation?token=${token}`)
  await page.getByLabel('Contraseña', { exact: true }).fill('e2e-vendor-password-123')
  await page.getByLabel('Confirma tu contraseña').fill('e2e-vendor-password-123')
  await page.getByRole('button', { name: 'Crear acceso' }).click()

  // 3. El "vendor_invited" Notification para este mismo contacto ya existe
  // (creado sincrónicamente al invitar, antes de que el proveedor siquiera
  // acepte) - visible en la campana del header, sin depender del gate de
  // Agreements (la campana vive fuera de RequireAgreementsAccepted).
  const bellButton = page.getByRole('button', { name: /^Notificaciones/ })
  await expect(bellButton).toHaveAccessibleName('Notificaciones (1 sin leer)')

  await bellButton.click()
  await expect(page.getByText('Invitación de proveedor')).toBeVisible()

  // Marking read keeps the dropdown open (onSelect preventDefault) - while
  // it's open, Radix aria-hides the rest of the page (including the
  // trigger) from the accessibility tree, so close it first before
  // re-querying the trigger's own accessible name.
  await page.getByText('Invitación de proveedor').click()
  await page.keyboard.press('Escape')
  await expect(bellButton).toHaveAccessibleName('Notificaciones')
})
