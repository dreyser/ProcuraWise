import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CommercialEvaluationPage } from './CommercialEvaluationPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

let mockRole = 'evaluation_owner'
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: mockRole, membership_id: 'owner-1' } }),
}))

function evaluationBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'eval-1',
    name: 'RFP asistido',
    description: '',
    status: 'evaluating',
    requirements: [],
    linked_vendor_count: 1,
    created_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    approval_status: 'approved',
    approver_membership_id: null,
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: null,
    ...overrides,
  }
}

function proposalBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'proposal-1',
    evaluation_id: 'eval-1',
    status: 'submitted',
    version: 1,
    round: 0,
    reopened_reason: null,
    reopened_at: null,
    reopened_by_membership_id: null,
    snapshots: [
      {
        snapshot_id: 'snap-1',
        taken_at: '2026-01-01T00:00:00Z',
        evaluation_id: 'eval-1',
        vendor_org_name: 'Proveedor Uno',
        evaluation_name: 'RFP asistido',
        vendor_org_id: 'vendor-1',
        requirements: [],
        answers: [],
        submitted_by_membership_id: 'vendor-membership-1',
        submitted_at: '2026-01-01T00:00:00Z',
        document_ids: [],
        round: 0,
        cost_items: [],
        tco_result: null,
      },
    ],
    ...overrides,
  }
}

function tcoBody() {
  return {
    base_currency: 'MXN',
    horizon_years: 1,
    by_year: { '1': '10000.00' },
    by_year_with_tax: { '1': '11600.00' },
    by_category: { initial: '10000.00' },
    grand_total: '10000.00',
    grand_total_with_tax: '11600.00',
    fx_rates_used: [],
    calculated_at: '2026-08-04T00:00:00Z',
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/proposals/proposal-1/commercial']}>
        <Routes>
          <Route
            path="/evaluations/:evaluationId/proposals/:proposalId/commercial"
            element={<CommercialEvaluationPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockCommon(
  router: ReturnType<typeof createFetchRouter>,
  overrides: Record<string, unknown> = {},
) {
  router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
  router.on('GET', /\/proposals\/proposal-1$/, () => ({
    status: 200,
    body: proposalBody(overrides),
  }))
  router.on('GET', /\/tco$/, () => ({ status: 200, body: tcoBody() }))
  router.on('GET', /\/economic-assessment$/, () => ({
    status: 404,
    body: { detail: 'Not Found' },
  }))
}

beforeEach(() => {
  mockRole = 'evaluation_owner'
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

// UAT-17 (R4): TCO and the commercial/risk EconomicAssessmentPanel used to
// live on two disconnected pages - this is the unified "Evaluación
// Comercial" view.
describe('CommercialEvaluationPage', () => {
  it('renders both TCO and the commercial/risk section together for the owner', async () => {
    const router = createFetchRouter()
    mockCommon(router)
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Proveedor Uno')).toBeInTheDocument()
    expect(await screen.findByText(/TCO \(1 año\(s\), MXN\)/)).toBeInTheDocument()
    expect(await screen.findByText('Condiciones comerciales y riesgo')).toBeInTheDocument()
  })

  it.each(['evaluator_functional', 'evaluator_technical'])(
    'hides the commercial/risk section from %s but still shows TCO (UAT-14)',
    async (role) => {
      mockRole = role
      const router = createFetchRouter()
      mockCommon(router)
      vi.stubGlobal('fetch', router.fetchImpl)

      renderPage()

      expect(await screen.findByText(/TCO \(1 año\(s\), MXN\)/)).toBeInTheDocument()
      expect(screen.queryByText('Condiciones comerciales y riesgo')).not.toBeInTheDocument()
    },
  )

  it('shows the commercial/risk section to evaluator_economic', async () => {
    mockRole = 'evaluator_economic'
    const router = createFetchRouter()
    mockCommon(router)
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Condiciones comerciales y riesgo')).toBeInTheDocument()
  })

  it('blocks access when the proposal has not been submitted yet', async () => {
    const router = createFetchRouter()
    mockCommon(router, { status: 'draft' })
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(
      await screen.findByText('Solo las propuestas enviadas tienen evaluación comercial.'),
    ).toBeInTheDocument()
  })
})
