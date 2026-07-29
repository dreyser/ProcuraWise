import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { DevActorSummary, EvaluationDetailResponse } from '@/api/client'

const OWNER_ID = 'membership-owner'
const VENDOR_ID = 'membership-vendor'

const DEV_ACTORS: DevActorSummary[] = [
  {
    actor_id: OWNER_ID,
    display_name: 'Owner A',
    tenant_name: 'Acme Compradora (dev)',
    role: 'evaluation_owner',
    vendor_org_id: null,
  },
  {
    actor_id: VENDOR_ID,
    display_name: 'Vendor Contact A',
    tenant_name: 'Acme Compradora (dev)',
    role: 'vendor_contact',
    vendor_org_id: 'vendor-1',
  },
]

function meFor(actorId: string) {
  const actor = DEV_ACTORS.find((a) => a.actor_id === actorId)!
  return {
    membership_id: actor.actor_id,
    user_id: 'user-1',
    tenant_id: 'tenant-1',
    tenant_name: actor.tenant_name,
    role: actor.role,
    vendor_org_id: actor.vendor_org_id,
    display_name: actor.display_name,
  }
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
  it('selects an actor, creates an evaluation, and lands on its detail page', async () => {
    const user = userEvent.setup()
    let evaluations: EvaluationDetailResponse[] = []

    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/dev\/actors$/, () => ({ status: 200, body: DEV_ACTORS }))
    router.on('GET', /\/api\/v1\/me$/, ({ headers }) => ({
      status: 200,
      body: meFor(headers.get('X-Dev-Membership-Id')!),
    }))
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

    await screen.findByRole('heading', { name: 'Selecciona un actor' })
    await user.click(await screen.findByRole('button', { name: /Owner A/ }))

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

describe('App integration - switching actor swaps role-scoped content', () => {
  it('never shows buyer data/actions once switched to a vendor_contact actor', async () => {
    const user = userEvent.setup()
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/dev\/actors$/, () => ({ status: 200, body: DEV_ACTORS }))
    router.on('GET', /\/api\/v1\/me$/, ({ headers }) => ({
      status: 200,
      body: meFor(headers.get('X-Dev-Membership-Id')!),
    }))
    router.on('GET', /\/api\/v1\/evaluations$/, () => ({ status: 200, body: [] }))
    router.on('GET', /\/api\/v1\/vendor-portal\/proposals$/, () => ({ status: 200, body: [] }))
    vi.stubGlobal('fetch', router.fetchImpl)

    render(<App />)

    await screen.findByRole('heading', { name: 'Selecciona un actor' })
    await user.click(await screen.findByRole('button', { name: /Owner A/ }))
    await screen.findByRole('heading', { name: 'Evaluaciones' })
    expect(screen.getByRole('link', { name: 'Nueva evaluación' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cambiar de actor' }))
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
    router.on('GET', /\/api\/v1\/dev\/actors$/, () => ({ status: 200, body: DEV_ACTORS }))
    router.on('GET', /\/api\/v1\/me$/, ({ headers }) => ({
      status: 200,
      body: meFor(headers.get('X-Dev-Membership-Id')!),
    }))
    router.on('GET', /\/api\/v1\/evaluations$/, () => ({
      status: 403,
      body: { detail: 'role not permitted' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    render(<App />)

    await screen.findByRole('heading', { name: 'Selecciona un actor' })
    await user.click(await screen.findByRole('button', { name: /Owner A/ }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No tienes permiso para realizar esta acción.')
    expect(alert).not.toHaveTextContent('role not permitted')
  })
})
