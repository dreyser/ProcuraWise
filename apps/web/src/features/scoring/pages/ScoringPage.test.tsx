import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ScoringPage } from './ScoringPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

let mockRole = 'evaluation_owner'
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: mockRole, membership_id: 'owner-1' } }),
}))

const REQUIREMENT_ID = 'req-1'

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
    snapshot: {
      snapshot_id: 'snap-1',
      vendor_org_name: 'Proveedor Uno',
      evaluation_name: 'RFP asistido',
      requirements: [
        {
          id: REQUIREMENT_ID,
          dimension: 'functional',
          category: 'Core',
          title: 'Soporta SSO',
          description: 'Debe soportar SSO via SAML.',
          priority: 'important',
          response_type: 'text',
          weight: 40,
          required: false,
          buyer_guidance: '',
          display_order: 1,
          options: [],
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      answers: [{ requirement_id: REQUIREMENT_ID, value: 'Si, via SAML.', vendor_comment: null }],
      document_ids: [],
    },
    ...overrides,
  }
}

function resultsBody(scores: unknown[] = []) {
  return {
    result_status: 'partial',
    is_final: false,
    scoring_status: 'incomplete',
    proposals: [
      {
        proposal_id: 'proposal-1',
        vendor_org_id: 'vendor-1',
        vendor_org_name: 'Proveedor Uno',
        status: 'submitted',
        functional: { earned_points: 0, maximum_points: 40 },
        technical: { earned_points: 0, maximum_points: 20 },
        economic: { status: 'not_available', earned_points: null, maximum_points: 40 },
        partial_result: { earned_points: 0, maximum_points: 60, model_coverage_percent: 60 },
        scores,
        mandatory_alerts_count: 0,
      },
    ],
    draft_proposals: [],
    disclaimer: '',
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/proposals/proposal-1/score']}>
        <Routes>
          <Route
            path="/evaluations/:evaluationId/proposals/:proposalId/score"
            element={<ScoringPage />}
          />
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

describe('ScoringPage', () => {
  it('renders the requirement with an empty score input for the owner', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/proposals\/proposal-1$/, () => ({ status: 200, body: proposalBody() }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Soporta SSO')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sugerir con IA' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar calificación' })).toBeDisabled()
  })

  it('hides the AI trigger and save controls for a non-owner buyer role', async () => {
    mockRole = 'internal_collaborator'
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/proposals\/proposal-1$/, () => ({ status: 200, body: proposalBody() }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Soporta SSO')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sugerir con IA' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar calificación' })).not.toBeInTheDocument()
  })

  it('triggers a suggestion, shows the candidate, and prefills the draft when used', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/proposals\/proposal-1$/, () => ({ status: 200, body: proposalBody() }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('POST', /\/ai\/score-suggestions$/, () => ({
      status: 202,
      body: {
        job_id: 'job-1',
        status_url: '/api/v1/evaluations/eval-1/proposals/proposal-1/ai/score-suggestions/job-1',
      },
    }))
    router.on('GET', /\/ai\/score-suggestions\/job-1$/, () => ({
      status: 200,
      body: {
        job_id: 'job-1',
        status: 'succeeded',
        candidates: [
          {
            requirement_id: REQUIREMENT_ID,
            suggested_score: 4,
            risk_flags: ['missing_evidence'],
            rationale: 'La respuesta no incluye evidencia suficiente.',
          },
        ],
        error: null,
        model: 'gpt-4o-mini',
        prompt_version: 'v1',
        token_usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        cost_estimate: null,
        latency_ms: 500,
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Soporta SSO')

    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))

    expect(await screen.findByText('Sugerencia de IA')).toBeInTheDocument()
    expect(screen.getByText('4', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Sin evidencia suficiente', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('La respuesta no incluye evidencia suficiente.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Usar esta sugerencia' }))

    expect(screen.getByRole('radio', { name: '4' })).toBeChecked()
    expect(screen.getByPlaceholderText('Comentario (opcional)')).toHaveValue(
      'La respuesta no incluye evidencia suficiente.',
    )
    expect(screen.getByRole('button', { name: 'Guardar calificación' })).toBeEnabled()
  })

  it('saves the accepted suggestion with source_ai_execution_id', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/proposals\/proposal-1$/, () => ({ status: 200, body: proposalBody() }))
    router.on('GET', /\/results$/, () => ({ status: 200, body: resultsBody() }))
    router.on('POST', /\/ai\/score-suggestions$/, () => ({
      status: 202,
      body: {
        job_id: 'job-1',
        status_url: '/api/v1/evaluations/eval-1/proposals/proposal-1/ai/score-suggestions/job-1',
      },
    }))
    router.on('GET', /\/ai\/score-suggestions\/job-1$/, () => ({
      status: 200,
      body: {
        job_id: 'job-1',
        status: 'succeeded',
        candidates: [
          {
            requirement_id: REQUIREMENT_ID,
            suggested_score: 4,
            risk_flags: [],
            rationale: 'Respuesta clara.',
          },
        ],
        error: null,
        model: 'gpt-4o-mini',
        prompt_version: 'v1',
        token_usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        cost_estimate: null,
        latency_ms: 500,
      },
    }))
    let capturedBody: Record<string, unknown> | undefined
    router.on('PUT', /\/scores\/req-1$/, async (ctx) => {
      capturedBody = ctx.body as Record<string, unknown>
      return {
        status: 200,
        body: {
          id: 'score-1',
          requirement_id: REQUIREMENT_ID,
          dimension: 'functional',
          priority: 'important',
          requirement_weight: 40,
          score: 4,
          comment: 'Respuesta clara.',
          weighted_points: 32,
          mandatory_alert: false,
          version: 1,
          created_by_membership_id: 'owner-1',
          updated_by_membership_id: 'owner-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          source_ai_execution_id: 'job-1',
        },
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Soporta SSO')
    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))
    await screen.findByText('Sugerencia de IA')
    await user.click(screen.getByRole('button', { name: 'Usar esta sugerencia' }))
    await user.click(screen.getByRole('button', { name: 'Guardar calificación' }))

    await vi.waitFor(() => expect(capturedBody?.source_ai_execution_id).toBe('job-1'))
    expect(capturedBody?.score).toBe(4)
  })
})
