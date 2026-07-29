import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { DevActorSummary, EvaluationDetailResponse } from '@/api/client'

const OWNER_ID = 'membership-owner'
const VENDOR_ID = 'membership-vendor'
const OWNER_EMAIL = 'owner.a@dev.procurawise.local'
const OWNER_PASSWORD = 'dev-password-2026'

const DEV_ACTORS: DevActorSummary[] = [
  {
    actor_id: VENDOR_ID,
    display_name: 'Vendor Contact A',
    tenant_name: 'Acme Compradora (dev)',
    role: 'vendor_contact',
    vendor_org_id: 'vendor-1',
  },
]

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
  it('logs in, creates an evaluation, and lands on its detail page', async () => {
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
    await user.click(screen.getByRole('button', { name: 'Crear evaluación' }))

    await screen.findByRole('heading', { name: 'RFP CRM' })
    expect(screen.getByText('Borrador')).toBeInTheDocument()
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

    // The vendor portal is a physically separate mechanism/URL (AUTH-PROD
    // scope decision #1 - vendor_contact stays on the interim dev-header
    // selector, not real login) - simulated here as a fresh visit to
    // /dev/select-actor, the same way a developer would exercise it
    // independently of any buyer session.
    const vendorRouter = createFetchRouter()
    vendorRouter.on('GET', /\/api\/v1\/dev\/actors$/, () => ({ status: 200, body: DEV_ACTORS }))
    vendorRouter.on('GET', /\/api\/v1\/me$/, ({ headers }) => ({
      status: 200,
      body: meFor(headers.get('X-Dev-Membership-Id')!),
    }))
    vendorRouter.on('GET', /\/api\/v1\/vendor-portal\/proposals$/, () => ({
      status: 200,
      body: [],
    }))
    vi.stubGlobal('fetch', vendorRouter.fetchImpl)
    window.history.pushState({}, '', '/dev/select-actor')

    render(<App />)
    await screen.findByRole('heading', { name: 'Selecciona un actor' })
    await user.click(await screen.findByRole('button', { name: /Vendor Contact A/ }))

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
