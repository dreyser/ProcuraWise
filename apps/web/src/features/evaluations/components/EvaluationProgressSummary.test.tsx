import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EvaluationProgressSummary } from './EvaluationProgressSummary'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { EvaluationDetailResponse } from '@/api/client'

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

function renderSummary(
  evaluation: EvaluationDetailResponse,
  router: ReturnType<typeof createFetchRouter>,
) {
  vi.stubGlobal('fetch', router.fetchImpl)
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <EvaluationProgressSummary evaluationId="eval-1" evaluation={evaluation} />
    </QueryClientProvider>,
  )
}

// UAT-04/09 (R3): consolidated blockers/next-action/per-evaluator completion.
describe('EvaluationProgressSummary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows draft blockers from weight/vendor readiness as the next action', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: { items: [] } }))
    renderSummary(buildEvaluation({ status: 'draft' }), router)

    expect(await screen.findByText('Estado consolidado')).toBeInTheDocument()
    // The first blocker doubles as "próxima acción" - appears once there and
    // once in the "Bloqueadores" list.
    expect(
      screen.getAllByText(/Los requerimientos funcionales deben sumar 40 puntos/),
    ).toHaveLength(2)
    expect(screen.getByText('Debes vincular al menos un proveedor.')).toBeInTheDocument()
  })

  it('reports vendors pending response in collecting_responses, with a count', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/proposals$/, () => ({
      status: 200,
      body: [
        {
          id: 'p1',
          evaluation_id: 'eval-1',
          vendor_org_id: 'v1',
          status: 'submitted',
          version: 1,
          round: 0,
          created_at: '',
          updated_at: '',
          submitted_at: '2026-01-01T00:00:00Z',
        },
        {
          id: 'p2',
          evaluation_id: 'eval-1',
          vendor_org_id: 'v2',
          status: 'draft',
          version: 1,
          round: 0,
          created_at: '',
          updated_at: '',
          submitted_at: null,
        },
      ],
    }))
    renderSummary(buildEvaluation({ status: 'collecting_responses' }), router)

    expect(await screen.findByText('1 de 2 proveedores no han respondido.')).toBeInTheDocument()
    expect(screen.getByText(/Espera a que respondan los proveedores restantes/)).toBeInTheDocument()
  })

  it('flags an overdue response deadline as an additional blocker', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/proposals$/, () => ({
      status: 200,
      body: [
        {
          id: 'p1',
          evaluation_id: 'eval-1',
          vendor_org_id: 'v1',
          status: 'draft',
          version: 1,
          round: 0,
          created_at: '',
          updated_at: '',
          submitted_at: null,
        },
      ],
    }))
    renderSummary(
      buildEvaluation({
        status: 'collecting_responses',
        response_deadline: '2020-01-01T00:00:00Z',
      }),
      router,
    )

    expect(await screen.findByText('La fecha límite de respuesta ya pasó.')).toBeInTheDocument()
  })

  it('shows scoring-incomplete and mandatory-alert blockers while evaluating', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/results$/, () => ({
      status: 200,
      body: {
        result_status: 'partial',
        is_final: false,
        scoring_status: 'incomplete',
        proposals: [
          {
            proposal_id: 'p1',
            vendor_org_id: 'v1',
            vendor_org_name: 'Proveedor Uno',
            status: 'submitted',
            functional: { earned_points: 0, maximum_points: 40 },
            technical: { earned_points: 0, maximum_points: 20 },
            economic: { status: 'not_available', earned_points: null, maximum_points: 40 },
            partial_result: { earned_points: 0, maximum_points: 60, model_coverage_percent: 0 },
            final_result: null,
            scores: [],
            mandatory_alerts_count: 2,
          },
        ],
        draft_proposals: [],
        disclaimer: '',
      },
    }))
    renderSummary(buildEvaluation({ status: 'evaluating' }), router)

    expect(
      await screen.findByText('Hay requerimientos sin calificar en al menos una propuesta.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('2 alerta(s) de requerimiento obligatorio sin cumplir.'),
    ).toBeInTheDocument()
  })

  it('shows no blockers and a closing next action once completed', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/org\/members$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/results$/, () => ({
      status: 200,
      body: {
        result_status: 'final',
        is_final: true,
        scoring_status: 'complete',
        proposals: [],
        draft_proposals: [],
        disclaimer: '',
      },
    }))
    renderSummary(buildEvaluation({ status: 'completed' }), router)

    expect(
      await screen.findByText(/Evaluación completada - revisa los resultados/),
    ).toBeInTheDocument()
    expect(screen.queryByText('Bloqueadores')).not.toBeInTheDocument()
  })

  it('lists per-evaluator self-reported completion from assignments', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/assignments$/, () => ({
      status: 200,
      body: {
        items: [
          {
            id: 'a1',
            evaluation_id: 'eval-1',
            dimension: 'functional',
            section: 'Core',
            evaluator_membership_id: 'eval-member-1',
            assigned_by_membership_id: 'owner-1',
            status: 'in_progress',
            created_at: '',
            updated_at: '',
          },
        ],
      },
    }))
    router.on('GET', /\/org\/members$/, () => ({
      status: 200,
      body: {
        items: [
          {
            membership_id: 'eval-member-1',
            user_id: 'u1',
            email: 'e@dev.local',
            display_name: 'Evaluador Funcional A',
            role: 'evaluator_functional',
          },
        ],
      },
    }))
    renderSummary(buildEvaluation({ status: 'evaluating' }), router)

    expect(await screen.findByText('Completitud por evaluador')).toBeInTheDocument()
    expect(await screen.findByText('Evaluador Funcional A')).toBeInTheDocument()
    expect(screen.getByText('En progreso')).toBeInTheDocument()
  })
})
