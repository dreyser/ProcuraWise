import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EvaluationApprovalPage } from './EvaluationApprovalPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { EvaluationDetailResponse, OrgMembersListResponse } from '@/api/client'

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
    requirements: [
      {
        id: 'req-1',
        dimension: 'functional',
        category: 'Core',
        title: 'Debe soportar SSO',
        description: '',
        priority: 'important',
        response_type: 'text',
        weight: 40,
        required: true,
        buyer_guidance: null,
        display_order: 1,
        options: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'req-2',
        dimension: 'technical',
        category: 'Core',
        title: 'Debe integrarse por API REST',
        description: '',
        priority: 'important',
        response_type: 'text',
        weight: 20,
        required: true,
        buyer_guidance: null,
        display_order: 2,
        options: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    linked_vendor_count: 1,
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

function orgMembers(): OrgMembersListResponse {
  return {
    items: [
      {
        membership_id: 'reviewer-1',
        user_id: 'user-reviewer-1',
        email: 'reviewer@dev.local',
        display_name: 'Colaborador Interno A',
        role: 'internal_collaborator',
      },
      {
        membership_id: 'approver-1',
        user_id: 'user-approver-1',
        email: 'approver@dev.local',
        display_name: 'Aprobador A',
        role: 'approver',
      },
    ],
  }
}

function mockBackend(
  router: ReturnType<typeof createFetchRouter>,
  evaluation: EvaluationDetailResponse,
) {
  router.on('GET', /\/api\/v1\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluation }))
  router.on('GET', /\/api\/v1\/org-members$/, () => ({ status: 200, body: orgMembers() }))
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/approval']}>
        <Routes>
          <Route path="/evaluations/:evaluationId/approval" element={<EvaluationApprovalPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ADR 0026 (R2): reviewer assignment + request-review + reviewer decision UI.
describe('EvaluationApprovalPage - review stage (ADR 0026)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows no-reviewer state to the owner when none is assigned yet', async () => {
    mockActor = { role: 'evaluation_owner', membership_id: 'owner-1' }
    const router = createFetchRouter()
    mockBackend(router, buildEvaluation())
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Revisión (opcional)')).toBeInTheDocument()
    expect(screen.getByText(/Sin revisor asignado/)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /Revisor/ })).toBeInTheDocument()
  })

  it('lets the owner request review once a reviewer is already assigned', async () => {
    mockActor = { role: 'evaluation_owner', membership_id: 'owner-1' }
    const router = createFetchRouter()
    mockBackend(router, buildEvaluation({ reviewer_membership_id: 'reviewer-1' }))
    let reviewRequested = false
    router.on('POST', /\/request-review$/, () => {
      reviewRequested = true
      return {
        status: 200,
        body: buildEvaluation({ reviewer_membership_id: 'reviewer-1', review_status: 'pending' }),
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    const requestButton = await screen.findByRole('button', { name: 'Solicitar revisión' })
    await vi.waitFor(() => expect(requestButton).toBeEnabled())
    await user.click(requestButton)

    await vi.waitFor(() => expect(reviewRequested).toBe(true))
  })

  it('shows the assigned reviewer their decision controls and lets them approve', async () => {
    mockActor = { role: 'internal_collaborator', membership_id: 'reviewer-1' }
    const router = createFetchRouter()
    mockBackend(
      router,
      buildEvaluation({ reviewer_membership_id: 'reviewer-1', review_status: 'pending' }),
    )
    let approved = false
    router.on('POST', /\/review\/approve$/, () => {
      approved = true
      return {
        status: 200,
        body: buildEvaluation({
          reviewer_membership_id: 'reviewer-1',
          review_status: 'approved',
        }),
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('Tu revisión')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/Comentario/), 'se ve bien')
    await user.click(screen.getByRole('button', { name: 'Aprobar revisión' }))

    await vi.waitFor(() => expect(approved).toBe(true))
  })

  it('relabels the reject button to "Solicitar cambios" once that checkbox is checked', async () => {
    mockActor = { role: 'internal_collaborator', membership_id: 'reviewer-1' }
    const router = createFetchRouter()
    mockBackend(
      router,
      buildEvaluation({ reviewer_membership_id: 'reviewer-1', review_status: 'pending' }),
    )
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Tu revisión')
    await user.type(screen.getByLabelText(/Comentario/), 'faltan detalles')
    expect(screen.getByRole('button', { name: 'Rechazar' })).toBeInTheDocument()

    await user.click(screen.getByLabelText('Es una solicitud de cambios, no un rechazo definitivo'))

    expect(screen.getByRole('button', { name: 'Solicitar cambios' })).toBeInTheDocument()
    expect(screen.getByLabelText('Debe soportar SSO')).toBeInTheDocument()
  })

  it('does not show reviewer decision controls to an internal_collaborator not assigned as reviewer', async () => {
    mockActor = { role: 'internal_collaborator', membership_id: 'someone-else' }
    const router = createFetchRouter()
    mockBackend(
      router,
      buildEvaluation({ reviewer_membership_id: 'reviewer-1', review_status: 'pending' }),
    )
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Revisión (opcional)')).toBeInTheDocument()
    expect(screen.queryByText('Tu revisión')).not.toBeInTheDocument()
  })
})
