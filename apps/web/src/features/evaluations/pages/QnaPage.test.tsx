import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QnaPage } from './QnaPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { BuyerQuestionResponse, EvaluationDetailResponse } from '@/api/client'

let mockRole = 'evaluation_owner'
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: mockRole, membership_id: 'owner-1' } }),
}))

function buildQuestion(overrides: Partial<BuyerQuestionResponse> = {}): BuyerQuestionResponse {
  return {
    id: 'q-1',
    proposal_id: 'proposal-1',
    vendor_org_id: 'vendor-org-1',
    requirement_id: null,
    scope: 'general',
    body: 'Cuando cierra el RFP?',
    status: 'open',
    version: 1,
    created_by_membership_id: 'contact-1',
    created_at: '2026-01-01T00:00:00Z',
    current_answer: null,
    answer_history: [],
    ...overrides,
  }
}

// Fase 28 remediación R1A (UAT-01): QnaPage now fetches the evaluation
// itself (for the shared header/EvaluationTabNav) - every test needs this
// mocked too, not just the questions list.
function buildEvaluation(
  overrides: Partial<EvaluationDetailResponse> = {},
): EvaluationDetailResponse {
  return {
    id: 'eval-1',
    name: 'RFP CRM',
    description: '',
    status: 'collecting_responses',
    requirements: [],
    linked_vendor_count: 1,
    created_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: '2026-01-01T00:00:00Z',
    evaluating_started_at: null,
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
    ...overrides,
  }
}

function mockEvaluation(
  router: ReturnType<typeof createFetchRouter>,
  overrides: Partial<EvaluationDetailResponse> = {},
) {
  router.on('GET', /\/api\/v1\/evaluations\/eval-1$/, () => ({
    status: 200,
    body: buildEvaluation(overrides),
  }))
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/qna']}>
        <Routes>
          <Route path="/evaluations/:evaluationId/qna" element={<QnaPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('QnaPage', () => {
  beforeEach(() => {
    mockRole = 'evaluation_owner'
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows an empty state when there are no questions', async () => {
    const router = createFetchRouter()
    mockEvaluation(router)
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Sin preguntas')).toBeInTheDocument()
  })

  it('shows an error banner when the list fails to load', async () => {
    const router = createFetchRouter()
    mockEvaluation(router)
    router.on('GET', /\/questions$/, () => ({ status: 404 }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('El recurso solicitado no está disponible.')).toBeInTheDocument()
  })

  it('lists questions with real vendor identity, grouped by status', async () => {
    const router = createFetchRouter()
    mockEvaluation(router)
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: {
        items: [
          buildQuestion({ id: 'q-open', body: 'Pregunta sin responder' }),
          buildQuestion({
            id: 'q-answered',
            body: 'Pregunta respondida',
            status: 'answered',
            current_answer: {
              version: 1,
              body: 'Cierra el 30 de agosto.',
              visibility: 'private',
              answered_by_membership_id: 'owner-1',
              answered_at: '2026-01-01T00:00:00Z',
            },
          }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Pregunta sin responder')).toBeInTheDocument()
    expect(screen.getByText('Pregunta respondida')).toBeInTheDocument()
    expect(screen.getAllByText('Cierra el 30 de agosto.').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/vendor-org-1/)).not.toHaveLength(0)
    expect(screen.getByText('Sin responder: 1 / 2')).toBeInTheDocument()
  })

  it('lets the owner publish an answer with a chosen visibility', async () => {
    const router = createFetchRouter()
    mockEvaluation(router)
    let published = false
    router.on('PUT', /\/questions\/q-1\/answer$/, () => {
      published = true
      return {
        status: 200,
        body: buildQuestion({
          status: 'answered',
          version: 2,
          current_answer: {
            version: 1,
            body: 'Cierra el 30 de agosto.',
            visibility: 'published_anonymized',
            answered_by_membership_id: 'owner-1',
            answered_at: '2026-01-01T00:00:00Z',
          },
        }),
      }
    })
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: {
        items: [
          published
            ? buildQuestion({
                status: 'answered',
                version: 2,
                current_answer: {
                  version: 1,
                  body: 'Cierra el 30 de agosto.',
                  visibility: 'published_anonymized',
                  answered_by_membership_id: 'owner-1',
                  answered_at: '2026-01-01T00:00:00Z',
                },
              })
            : buildQuestion(),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Cuando cierra el RFP?')

    await user.type(screen.getByPlaceholderText('Escribe la respuesta…'), 'Cierra el 30 de agosto.')
    await user.click(screen.getByLabelText('Publicada (anónima)'))
    await user.click(screen.getByRole('button', { name: 'Publicar respuesta' }))

    await vi.waitFor(() => expect(published).toBe(true))
    expect(await screen.findAllByText('Publicada (anónima)')).not.toHaveLength(0)
  })

  it('shows a conflict message on a stale version and allows reloading', async () => {
    const router = createFetchRouter()
    mockEvaluation(router)
    router.on('PUT', /\/questions\/q-1\/answer$/, () => ({ status: 409 }))
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [buildQuestion()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Cuando cierra el RFP?')

    await user.type(screen.getByPlaceholderText('Escribe la respuesta…'), 'Respuesta')
    await user.click(screen.getByRole('button', { name: 'Publicar respuesta' }))

    expect(
      await screen.findByText('Los datos cambiaron desde que cargaste esta pregunta.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument()
  })

  it('hides the answer form for a non-owner buyer role but still shows the list', async () => {
    mockRole = 'evaluator_functional'
    const router = createFetchRouter()
    mockEvaluation(router)
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [buildQuestion()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Cuando cierra el RFP?')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Escribe la respuesta…')).not.toBeInTheDocument()
    expect(
      screen.getByText('Tu rol puede revisar esta sección, pero no puede responder ni publicar.'),
    ).toBeInTheDocument()
  })
})
