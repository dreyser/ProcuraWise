import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { EvaluationDetailResponse } from '@/api/client'

const OWNER_ID = 'membership-owner'
const VENDOR_ID = 'membership-vendor'
const OWNER_EMAIL = 'owner.a@dev.procurawise.local'
const OWNER_PASSWORD = 'dev-password-2026'
const VENDOR_EMAIL = 'vendor.a@dev.procurawise.local'
const VENDOR_PASSWORD = 'dev-vendor-password-2026'

function meFor(actorId: string) {
  const known: Record<string, ReturnType<typeof buildActor>> = {
    [OWNER_ID]: buildActor({
      membership_id: OWNER_ID,
      role: 'evaluation_owner',
      display_name: 'Owner A',
      vendor_org_id: null,
    }),
    [VENDOR_ID]: buildActor({
      membership_id: VENDOR_ID,
      role: 'vendor_contact',
      display_name: 'Vendor Contact A',
      vendor_org_id: 'vendor-1',
    }),
  }
  return known[actorId]
}

function buildActor(overrides: {
  membership_id: string
  role: string
  display_name: string
  vendor_org_id: string | null
}) {
  return {
    membership_id: overrides.membership_id,
    user_id: 'user-1',
    tenant_id: 'tenant-1',
    tenant_name: 'Acme Compradora (dev)',
    role: overrides.role,
    vendor_org_id: overrides.vendor_org_id,
    display_name: overrides.display_name,
  }
}

/** Registers the three /auth/* endpoints a single-membership password login
 * needs, all the way to a real access token - the buyer identity mechanism
 * after AUTH-PROD (replaces the old dev-header selector for buyer roles). */
function mockOwnerLogin(router: ReturnType<typeof createFetchRouter>) {
  router.on('POST', /\/api\/v1\/auth\/login$/, () => ({
    status: 200,
    body: { pre_session_token: 'pre-session-1', token_type: 'bearer', expires_in: 300 },
  }))
  router.on('GET', /\/api\/v1\/auth\/memberships$/, () => ({
    status: 200,
    body: {
      memberships: [
        {
          membership_id: OWNER_ID,
          tenant_id: 'tenant-1',
          tenant_name: 'Acme Compradora (dev)',
          role: 'evaluation_owner',
          display_name: 'Owner A',
        },
      ],
    },
  }))
  router.on('POST', /\/api\/v1\/auth\/switch-tenant$/, () => ({
    status: 200,
    body: {
      access_token: 'access-token-1',
      token_type: 'bearer',
      expires_in: 1800,
      actor: meFor(OWNER_ID),
    },
  }))
}

async function loginAsOwner(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('heading', { name: /iniciar sesión/i })
  await user.type(screen.getByLabelText('Correo'), OWNER_EMAIL)
  await user.type(screen.getByLabelText('Contraseña'), OWNER_PASSWORD)
  await user.click(screen.getByRole('button', { name: 'Entrar' }))
}

function buildEvaluationDetail(
  overrides: Partial<EvaluationDetailResponse>,
): EvaluationDetailResponse {
  return {
    id: 'eval-1',
    name: 'RFP CRM',
    description: '',
    status: 'draft',
    requirements: [],
    linked_vendor_count: 0,
    created_by_membership_id: OWNER_ID,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: null,
    completed_at: null,
    approval_status: 'not_requested',
    approver_membership_id: null,
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: null,
    base_currency: 'MXN',
    tco_horizon_years: 1,
    economic_criteria_weights: {
      commercial: {
        payment_terms: 25,
        price_protection: 25,
        contractual_flexibility: 20,
        discounts_incentives: 15,
        billing_transparency: 15,
      },
      risk: {
        variable_cost_exposure: 30,
        increases_indexation: 25,
        assumptions_exclusions: 20,
        fx_fiscal_regulatory: 15,
        exit_portability_lockin: 10,
      },
    },
    reviewer_membership_id: null,
    review_status: 'not_requested',
    review_requested_at: null,
    review_requested_by_membership_id: null,
    review_decided_at: null,
    review_decided_by_membership_id: null,
    review_comment: null,
    ...overrides,
  }
}

beforeEach(() => {
  sessionStorage.clear()
  // The app uses BrowserRouter (real jsdom history), which - unlike
  // component state - is not reset between tests by Testing Library's
  // cleanup, so the URL a previous test navigated to would otherwise leak
  // into the next one.
  window.history.pushState({}, '', '/')
})

describe('App integration - owner creates an evaluation', () => {
  it('logs in, creates an evaluation through the wizard, and advances to the requirements step', async () => {
    const user = userEvent.setup()
    let evaluations: EvaluationDetailResponse[] = []

    const router = createFetchRouter()
    mockOwnerLogin(router)
    router.on('GET', /\/api\/v1\/evaluations$/, () => ({
      status: 200,
      body: evaluations.map((e) => ({
        id: e.id,
        name: e.name,
        status: e.status,
        linked_vendor_count: e.linked_vendor_count,
        created_at: e.created_at,
        updated_at: e.updated_at,
      })),
    }))
    router.on('POST', /\/api\/v1\/evaluations$/, ({ body }) => {
      const created = buildEvaluationDetail({
        id: 'eval-1',
        name: (body as { name: string }).name,
        description: (body as { description?: string }).description ?? '',
      })
      evaluations = [created]
      return { status: 201, body: created }
    })
    router.on('GET', /\/api\/v1\/evaluations\/eval-1$/, () => ({
      status: 200,
      body: evaluations[0],
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    render(<App />)
    await loginAsOwner(user)

    await screen.findByRole('heading', { name: 'Evaluaciones' })
    expect(await screen.findByText('Todavía no hay evaluaciones')).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'Nueva evaluación' }))
    await screen.findByRole('heading', { name: 'Nueva evaluación' })

    await user.type(screen.getByLabelText('Nombre'), 'RFP CRM')
    await user.click(screen.getByRole('button', { name: 'Crear y continuar' }))

    await screen.findByRole('heading', { name: 'RFP CRM' })
    expect(screen.getByText('Borrador')).toBeInTheDocument()
    // Creating advances the wizard straight to step 2 (Requerimientos) on
    // the same evaluation, rather than landing on the read-only detail page.
    expect(await screen.findByRole('heading', { name: 'Funcional' })).toBeInTheDocument()
  })
})

describe('App integration - buyer and vendor identities never leak into each other', () => {
  it('never shows buyer data/actions in the vendor portal, or vice versa', async () => {
    const user = userEvent.setup()

    const buyerRouter = createFetchRouter()
    mockOwnerLogin(buyerRouter)
    buyerRouter.on('GET', /\/api\/v1\/evaluations$/, () => ({ status: 200, body: [] }))
    vi.stubGlobal('fetch', buyerRouter.fetchImpl)

    const buyerRender = render(<App />)
    await loginAsOwner(user)
    await screen.findByRole('heading', { name: 'Evaluaciones' })
    expect(screen.getByRole('link', { name: 'Nueva evaluación' })).toBeInTheDocument()
    buyerRender.unmount()

    // The vendor portal is a physically separate mechanism/URL (Fase 15:
    // real vendor login, token_use=vendor_access) - simulated here as a
    // fresh visit to /vendor/login, the same way a real vendor contact
    // would reach it independently of any buyer session.
    const vendorRouter = createFetchRouter()
    vendorRouter.on('POST', /\/api\/v1\/vendor-auth\/login$/, () => ({
      status: 200,
      body: {
        access_token: 'vendor-access-token-1',
        token_type: 'bearer',
        expires_in: 1800,
        actor: meFor(VENDOR_ID),
      },
    }))
    vendorRouter.on('GET', /\/api\/v1\/vendor-portal\/agreements\/status$/, () => ({
      status: 200,
      body: {
        nda_accepted: true,
        conflict_of_interest_accepted: true,
        current_nda_version: 'v1',
        current_conflict_of_interest_version: 'v1',
        nda_text: 'nda',
        conflict_of_interest_text: 'coi',
      },
    }))
    vendorRouter.on('GET', /\/api\/v1\/vendor-portal\/proposals$/, () => ({
      status: 200,
      body: [],
    }))
    vi.stubGlobal('fetch', vendorRouter.fetchImpl)
    window.history.pushState({}, '', '/vendor/login')

    render(<App />)
    await screen.findByRole('heading', { name: 'Acceso de proveedor' })
    await user.type(screen.getByLabelText('Correo'), VENDOR_EMAIL)
    await user.type(screen.getByLabelText('Contraseña'), VENDOR_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await screen.findByRole('heading', { name: 'Mis propuestas' })
    expect(screen.queryByRole('link', { name: 'Nueva evaluación' })).not.toBeInTheDocument()
    expect(screen.queryByText('Evaluaciones')).not.toBeInTheDocument()
    expect(screen.getByText(/Vendor Contact A/)).toBeInTheDocument()
  })
})

describe('App integration - error normalization end to end', () => {
  it('shows a normalized banner (not a raw backend message) when the evaluations list 403s', async () => {
    const user = userEvent.setup()
    const router = createFetchRouter()
    mockOwnerLogin(router)
    router.on('GET', /\/api\/v1\/evaluations$/, () => ({
      status: 403,
      body: { detail: 'role not permitted' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    render(<App />)
    await loginAsOwner(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No tienes permiso para realizar esta acción.')
    expect(alert).not.toHaveTextContent('role not permitted')
  })
})
