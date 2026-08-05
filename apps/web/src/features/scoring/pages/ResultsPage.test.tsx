import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResultsPage } from './ResultsPage'
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
    requirements: [{ id: 'req-1' }],
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

function proposalResult(overrides: Record<string, unknown> = {}) {
  return {
    proposal_id: 'proposal-1',
    vendor_org_id: 'vendor-1',
    vendor_org_name: 'Proveedor Uno',
    status: 'submitted',
    functional: { earned_points: 40, maximum_points: 40 },
    technical: { earned_points: 20, maximum_points: 20 },
    economic: { status: 'not_available', earned_points: null, maximum_points: 40 },
    partial_result: { earned_points: 60, maximum_points: 60, model_coverage_percent: 60 },
    final_result: null,
    scores: [{ requirement_id: 'req-1' }],
    mandatory_alerts_count: 0,
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/results']}>
        <Routes>
          <Route path="/evaluations/:evaluationId/results" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockRole = 'evaluation_owner'
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ResultsPage', () => {
  it('shows "No disponible" for economic and final result while the economic assessment is pending', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/results$/, () => ({
      status: 200,
      body: {
        result_status: 'partial',
        is_final: false,
        scoring_status: 'incomplete',
        proposals: [proposalResult()],
        draft_proposals: [],
        disclaimer: 'Resultado parcial. No constituye recomendacion de adjudicacion.',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Proveedor Uno')).toBeInTheDocument()
    const noDisponible = screen.getAllByText('No disponible')
    expect(noDisponible).toHaveLength(2) // economic column + final result column
    expect(screen.getByRole('button', { name: 'Completar evaluación' })).toBeDisabled()
    expect(screen.getByText(/evaluación económica incompleta/)).toBeInTheDocument()
  })

  it('shows the real economic and final result once both are available', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/results$/, () => ({
      status: 200,
      body: {
        result_status: 'final',
        is_final: true,
        scoring_status: 'complete',
        proposals: [
          proposalResult({
            economic: { status: 'available', earned_points: 26, maximum_points: 40 },
            final_result: { total_points: 86, maximum_points: 100 },
          }),
        ],
        draft_proposals: [],
        disclaimer: 'Resultado final. No constituye recomendacion de adjudicacion.',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    const row = (await screen.findByText('Proveedor Uno')).closest('tr')
    expect(row).not.toBeNull()
    const cells = within(row!).getAllByRole('cell')
    expect(cells[3]).toHaveTextContent('26 / 40') // Económico
    expect(cells[5]).toHaveTextContent('86 / 100') // Resultado final
    expect(screen.getByRole('button', { name: 'Completar evaluación' })).toBeEnabled()
  })

  it('completes the evaluation once the owner confirms', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/results$/, () => ({
      status: 200,
      body: {
        result_status: 'final',
        is_final: true,
        scoring_status: 'complete',
        proposals: [
          proposalResult({
            economic: { status: 'available', earned_points: 40, maximum_points: 40 },
            final_result: { total_points: 100, maximum_points: 100 },
          }),
        ],
        draft_proposals: [],
        disclaimer: '',
      },
    }))
    router.on('POST', /\/complete$/, () => ({
      status: 200,
      body: evaluationBody({ status: 'completed' }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Proveedor Uno')

    await user.click(screen.getByRole('button', { name: 'Completar evaluación' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Completar evaluación' }))

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
