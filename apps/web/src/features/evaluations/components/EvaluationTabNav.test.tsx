import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EvaluationTabNav } from './EvaluationTabNav'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  type EvaluationDetailResponse,
} from '@/api/client'

let mockActor: { role: string; membership_id: string } | null = null
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: mockActor }),
}))

function buildEvaluation(
  overrides: Partial<EvaluationDetailResponse> = {},
): EvaluationDetailResponse {
  return {
    id: 'eval-1',
    name: 'RFP CRM',
    description: '',
    status: 'draft',
    requirements: [],
    linked_vendor_count: 0,
    created_by_membership_id: 'owner-1',
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

function renderNav(evaluation: EvaluationDetailResponse) {
  const router = createFetchRouter()
  router.on('GET', /\/api\/v1\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluation }))
  vi.stubGlobal('fetch', router.fetchImpl)

  const queryClient = createAppQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/evaluations/eval-1']}>
        <EvaluationTabNav evaluationId="eval-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

// Waits for the evaluation query's cache entry itself, not just a DOM
// element that renders unconditionally on first paint (e.g.
// "Requerimientos") - the only reliable signal that canSeeApprovalTab has
// actually been computed from real data, which matters for the "hides"
// cases below where nothing else in the DOM changes to prove it.
async function waitForEvaluationLoaded(queryClient: ReturnType<typeof createAppQueryClient>) {
  await vi.waitFor(() =>
    expect(
      queryClient.getQueryData(getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey('eval-1')),
    ).toBeDefined(),
  )
}

// UAT-08 (ADR 0026, R2): "Aprobación" must only be visible to an actor who
// can actually act on it there.
describe('EvaluationTabNav', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // "Requerimientos" renders unconditionally on first paint, before the
  // evaluation query resolves - it is not a valid signal that the query
  // (and therefore canSeeApprovalTab) has settled. Every case below
  // `findByText`/`waitFor`s on "Aprobación" itself instead, in whichever
  // direction is actually being asserted.

  it('always shows Aprobación to the evaluation_owner', async () => {
    mockActor = { role: 'evaluation_owner', membership_id: 'owner-1' }
    renderNav(buildEvaluation())

    expect(await screen.findByText('Aprobación')).toBeInTheDocument()
  })

  it('shows Aprobación to the assigned approver', async () => {
    mockActor = { role: 'approver', membership_id: 'approver-1' }
    renderNav(buildEvaluation({ approver_membership_id: 'approver-1' }))

    expect(await screen.findByText('Aprobación')).toBeInTheDocument()
  })

  it('hides Aprobación from an approver role not assigned to this evaluation', async () => {
    mockActor = { role: 'approver', membership_id: 'someone-else' }
    const queryClient = renderNav(buildEvaluation({ approver_membership_id: 'approver-1' }))

    await waitForEvaluationLoaded(queryClient)
    expect(screen.queryByText('Aprobación')).not.toBeInTheDocument()
  })

  it('shows Aprobación to the assigned reviewer (ADR 0026)', async () => {
    mockActor = { role: 'internal_collaborator', membership_id: 'reviewer-1' }
    renderNav(buildEvaluation({ reviewer_membership_id: 'reviewer-1' }))

    expect(await screen.findByText('Aprobación')).toBeInTheDocument()
  })

  it('hides Aprobación from an internal_collaborator not assigned as reviewer', async () => {
    mockActor = { role: 'internal_collaborator', membership_id: 'someone-else' }
    const queryClient = renderNav(buildEvaluation({ reviewer_membership_id: 'reviewer-1' }))

    await waitForEvaluationLoaded(queryClient)
    expect(screen.queryByText('Aprobación')).not.toBeInTheDocument()
  })

  it('hides Aprobación from an evaluator role entirely', async () => {
    mockActor = { role: 'evaluator_functional', membership_id: 'eval-1' }
    const queryClient = renderNav(buildEvaluation())

    await waitForEvaluationLoaded(queryClient)
    expect(screen.queryByText('Aprobación')).not.toBeInTheDocument()
  })
})
