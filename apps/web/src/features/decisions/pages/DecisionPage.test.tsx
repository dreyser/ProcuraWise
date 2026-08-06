import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DecisionPage } from './DecisionPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

let mockRole = 'evaluation_owner'
let mockMembershipId = 'owner-1'
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: mockRole, membership_id: mockMembershipId } }),
}))

function evaluationBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'eval-1',
    name: 'RFP con decisión',
    description: '',
    status: 'completed',
    requirements: [{ id: 'req-1' }],
    linked_vendor_count: 1,
    created_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-02T00:00:00Z',
    approval_status: 'approved',
    approver_membership_id: 'publication-approver-1',
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: 'eval-1',
    ...overrides,
  }
}

function decisionBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'eval-1',
    evaluation_id: 'eval-1',
    status: 'not_requested',
    outcome: null,
    selected_vendor_org_id: null,
    selected_proposal_id: null,
    selected_proposal_snapshot_id: null,
    void_reason: null,
    justification: null,
    approver_membership_id: null,
    created_by_membership_id: 'owner-1',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    decision_snapshot_id: null,
    ...overrides,
  }
}

function resultsBody() {
  return {
    result_status: 'final',
    is_final: true,
    scoring_status: 'complete',
    proposals: [
      {
        proposal_id: 'proposal-1',
        vendor_org_id: 'vendor-1',
        vendor_org_name: 'Proveedor Uno',
        status: 'submitted',
        functional: { earned_points: 40, maximum_points: 40 },
        technical: { earned_points: 20, maximum_points: 20 },
        economic: { status: 'available', earned_points: 40, maximum_points: 40 },
        partial_result: { earned_points: 60, maximum_points: 60, model_coverage_percent: 60 },
        final_result: { total_points: 100, maximum_points: 100 },
        scores: [],
        mandatory_alerts_count: 0,
      },
    ],
    draft_proposals: [],
    disclaimer: 'Resultado final. No constituye recomendacion de adjudicacion.',
  }
}

function readinessBody(overrides: Record<string, unknown> = {}) {
  return {
    evaluation_completed: true,
    decision_exists: true,
    decision_status: 'not_requested',
    can_create: false,
    can_edit: true,
    can_request_approval: false,
    request_approval_reasons: ['an outcome (a selected vendor, or void) must be chosen'],
    can_approve_or_reject: false,
    suggested_approver_membership_id: 'publication-approver-1',
    ...overrides,
  }
}

function orgMembersBody() {
  return {
    items: [
      {
        membership_id: 'decision-approver-1',
        display_name: 'Aprobador Decisión',
        role: 'approver',
      },
      {
        membership_id: 'publication-approver-1',
        display_name: 'Aprobador Publicación',
        role: 'approver',
      },
    ],
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/decision']}>
        <Routes>
          <Route path="/evaluations/:evaluationId/decision" element={<DecisionPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockRole = 'evaluation_owner'
  mockMembershipId = 'owner-1'
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DecisionPage', () => {
  it('shows a waiting message while the evaluation is not completed', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({
      status: 200,
      body: evaluationBody({ status: 'evaluating' }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(
      await screen.findByText(/La decisión estará disponible cuando la evaluación esté completada/),
    ).toBeInTheDocument()
  })

  it('lets the owner start a decision once the evaluation is completed and none exists yet', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/decision\/readiness$/, () => ({
      status: 200,
      body: readinessBody({ decision_exists: false, can_create: true, decision_status: null }),
    }))
    router.on('GET', /\/decision$/, () => ({ status: 404, body: { detail: 'not found' } }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: orgMembersBody() }))
    router.on('POST', /\/decision$/, () => ({ status: 201, body: decisionBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    const startButton = await screen.findByRole('button', { name: 'Iniciar decisión' })
    await user.click(startButton)
  })

  it('lets the owner select a vendor, save, and request approval', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/decision\/readiness$/, () => ({ status: 200, body: readinessBody() }))
    router.on('GET', /\/decision$/, () => ({ status: 200, body: decisionBody() }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: orgMembersBody() }))
    router.on('PATCH', /\/decision$/, () => ({
      status: 200,
      body: decisionBody({
        outcome: 'selected',
        selected_vendor_org_id: 'vendor-1',
        justification: 'El proveedor cumple todos los requisitos y su TCO es el menor.',
      }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Proveedor Uno')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar selección' })).toBeDisabled()
  })

  it('lets the assigned decision approver approve, distinct from the publication approver', async () => {
    mockRole = 'approver'
    mockMembershipId = 'decision-approver-1'

    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/decision\/readiness$/, () => ({
      status: 200,
      body: readinessBody({ decision_status: 'pending', can_approve_or_reject: true }),
    }))
    router.on('GET', /\/decision$/, () => ({
      status: 200,
      body: decisionBody({
        status: 'pending',
        outcome: 'selected',
        selected_vendor_org_id: 'vendor-1',
        justification: 'El proveedor cumple todos los requisitos y su TCO es el menor.',
        approver_membership_id: 'decision-approver-1',
      }),
    }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('POST', /\/decision\/approve$/, () => ({
      status: 200,
      body: decisionBody({
        status: 'approved',
        outcome: 'selected',
        selected_vendor_org_id: 'vendor-1',
        approver_membership_id: 'decision-approver-1',
        decision_snapshot_id: 'eval-1',
      }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    const approveButton = await screen.findByRole('button', { name: 'Aprobar' })
    await user.click(approveButton)
  })

  it('shows the frozen memo de cierre once the decision is approved', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/decision\/readiness$/, () => ({
      status: 200,
      body: readinessBody({ decision_status: 'approved' }),
    }))
    router.on('GET', /\/decision$/, () => ({
      status: 200,
      body: decisionBody({
        status: 'approved',
        outcome: 'selected',
        selected_vendor_org_id: 'vendor-1',
        approver_membership_id: 'decision-approver-1',
        decision_snapshot_id: 'eval-1',
      }),
    }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('GET', /\/decision\/snapshot$/, () => ({
      status: 200,
      body: {
        snapshot_id: 'eval-1',
        evaluation_id: 'eval-1',
        outcome: 'selected',
        selected_vendor_org_id: 'vendor-1',
        selected_vendor_org_name: 'Proveedor Uno',
        selected_proposal_id: 'proposal-1',
        selected_proposal_snapshot_id: 'snap-0',
        void_reason: null,
        justification: 'El proveedor cumple todos los requisitos y su TCO es el menor.',
        approver_membership_id: 'decision-approver-1',
        decided_at: '2026-01-03T00:00:00Z',
        decided_by_membership_id: 'decision-approver-1',
        proposal_results: [],
        taken_at: '2026-01-03T00:00:00Z',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Memo de cierre')).toBeInTheDocument()
    const memo = (await screen.findByText(/Justificación:/)).closest('div')
    expect(memo).not.toBeNull()
    expect(within(memo!).getByText(/es de solo lectura/)).toBeInTheDocument()
  })
})
