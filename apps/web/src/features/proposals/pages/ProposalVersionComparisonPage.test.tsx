import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProposalVersionComparisonPage } from './ProposalVersionComparisonPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

const REQUIREMENT_ID = 'req-1'

function snapshot(round: number, overrides: Record<string, unknown> = {}) {
  return {
    snapshot_id: `snap-${round}`,
    taken_at: '2026-01-01T00:00:00Z',
    evaluation_id: 'eval-1',
    evaluation_name: 'RFP asistido',
    vendor_org_id: 'vendor-1',
    vendor_org_name: 'Proveedor Uno',
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
    answers: [
      {
        requirement_id: REQUIREMENT_ID,
        value: round === 0 ? 'Si, via SAML.' : 'Si, via SAML y OIDC.',
        vendor_comment: null,
        updated_at: '2026-01-01T00:00:00Z',
        status: round === 0 ? 'modified' : 'modified',
        source_proposal_version: round === 0 ? null : 0,
      },
    ],
    submitted_by_membership_id: 'vendor-membership-1',
    submitted_at: '2026-01-01T00:00:00Z',
    document_ids: [],
    round,
    cost_items: [
      {
        id: 'cost-1',
        concept: 'Licencia anual',
        category: 'recurring',
        description: null,
        billing_unit: 'usuario',
        quantity: round === 0 ? '10' : '20',
        unit_price: '100',
        currency: 'MXN',
        frequency_per_year: '1',
        tax_pct: '0',
        discount_pct: '0',
        year_start: 1,
        year_end: 1,
        annual_increment_pct: '0',
        mandatory: true,
        cost_type: 'recurring',
        notes: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        status: round === 0 ? 'modified' : 'modified',
        source_proposal_version: round === 0 ? null : 0,
      },
    ],
    tco_result: {
      base_currency: 'MXN',
      horizon_years: 1,
      by_year: { '1': round === 0 ? '1000.00' : '2000.00' },
      by_year_with_tax: { '1': round === 0 ? '1000.00' : '2000.00' },
      by_category: {},
      grand_total: round === 0 ? '1000.00' : '2000.00',
      grand_total_with_tax: round === 0 ? '1000.00' : '2000.00',
      fx_rates_used: [],
      calculated_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  }
}

function proposalBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'proposal-1',
    evaluation_id: 'eval-1',
    vendor_org_id: 'vendor-1',
    status: 'submitted',
    version: 5,
    round: 1,
    answers: [],
    snapshots: [snapshot(0), snapshot(1)],
    reopened_reason: 'Negociación de precio',
    reopened_at: '2026-02-01T00:00:00Z',
    reopened_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    submitted_at: '2026-02-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/proposals/proposal-1/versions']}>
        <Routes>
          <Route
            path="/evaluations/:evaluationId/proposals/:proposalId/versions"
            element={<ProposalVersionComparisonPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProposalVersionComparisonPage', () => {
  it('shows the answer, cost item, and TCO diff between Ronda 0 and Ronda 1', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/proposals\/proposal-1$/, () => ({ status: 200, body: proposalBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Comparación de rondas — Proveedor Uno')).toBeInTheDocument()
    expect(screen.getByText('Motivo de la reapertura: Negociación de precio')).toBeInTheDocument()

    expect(screen.getByText('Si, via SAML.')).toBeInTheDocument()
    expect(screen.getByText('Si, via SAML y OIDC.')).toBeInTheDocument()
    expect(screen.getByText('Modificada')).toBeInTheDocument()

    expect(screen.getByText('10 × 100 MXN')).toBeInTheDocument()
    expect(screen.getByText('20 × 100 MXN')).toBeInTheDocument()

    expect(screen.getByText('1000.00 MXN')).toBeInTheDocument()
    expect(screen.getByText('2000.00 MXN')).toBeInTheDocument()
  })

  it('shows an empty state when the proposal has never been reopened', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/proposals\/proposal-1$/, () => ({
      status: 200,
      body: proposalBody({ round: 0, snapshots: [snapshot(0)] }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(
      await screen.findByText('Esta propuesta no tiene rondas de negociación'),
    ).toBeInTheDocument()
  })
})
