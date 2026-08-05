import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CostItemsPanel } from './CostItemsPanel'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { CostItemResponse, VendorProposalDetailResponse } from '@/api/client'

function buildCostItem(overrides: Partial<CostItemResponse> = {}): CostItemResponse {
  return {
    id: 'item-1',
    concept: 'Licencias anuales',
    category: 'recurring',
    description: null,
    billing_unit: 'usuario',
    quantity: '10',
    unit_price: '199.99',
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
    status: 'modified',
    source_proposal_version: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function buildProposal(
  overrides: Partial<VendorProposalDetailResponse> = {},
): VendorProposalDetailResponse {
  return {
    id: 'proposal-1',
    evaluation_id: 'eval-1',
    evaluation_name: 'RFP CRM',
    status: 'draft',
    version: 1,
    round: 0,
    requirements: [],
    answers: [],
    cost_items: [],
    reopened_reason: null,
    reopened_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    submitted_at: null,
    ...overrides,
  }
}

function renderPanel(proposal: VendorProposalDetailResponse, disabled = false) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <CostItemsPanel proposalId={proposal.id} proposal={proposal} disabled={disabled} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CostItemsPanel', () => {
  it('shows an empty state when there are no cost items', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/tco-preview$/, () => ({
      status: 200,
      body: {
        base_currency: 'MXN',
        horizon_years: 1,
        by_year: {},
        by_year_with_tax: {},
        by_category: {},
        grand_total: '0.00',
        grand_total_with_tax: '0.00',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel(buildProposal())

    expect(await screen.findByText('Sin partidas')).toBeInTheDocument()
  })

  it('lists existing cost items and shows the TCO preview total', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/tco-preview$/, () => ({
      status: 200,
      body: {
        base_currency: 'MXN',
        horizon_years: 1,
        by_year: { '1': '1999.90' },
        by_year_with_tax: { '1': '1999.90' },
        by_category: { recurring: '1999.90' },
        grand_total: '1999.90',
        grand_total_with_tax: '1999.90',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel(buildProposal({ cost_items: [buildCostItem()] }))

    expect(await screen.findByText('Licencias anuales')).toBeInTheDocument()
    expect(await screen.findByText(/1999\.90/)).toBeInTheDocument()
  })

  it('submits the new cost item to the backend and closes the form on success', async () => {
    // CostItemsPanel renders `proposal.cost_items` from the prop its parent
    // (VendorProposalDetailPage) owns and re-fetches after a mutation - this
    // isolated test verifies the request/response contract and the form's
    // own success behavior, not a table refresh that depends on the parent.
    const router = createFetchRouter()
    router.on('GET', /\/tco-preview$/, () => ({
      status: 200,
      body: {
        base_currency: 'MXN',
        horizon_years: 1,
        by_year: {},
        by_year_with_tax: {},
        by_category: {},
        grand_total: '0.00',
        grand_total_with_tax: '0.00',
      },
    }))
    let postedBody: unknown = null
    router.on('POST', /\/cost-items$/, ({ body }) => {
      postedBody = body
      return {
        status: 200,
        body: buildProposal({ version: 2, cost_items: [buildCostItem({ concept: 'Soporte' })] }),
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel(buildProposal())

    await user.click(screen.getByRole('button', { name: 'Agregar partida de costo' }))
    await user.type(screen.getByLabelText('Concepto'), 'Soporte')
    await user.type(screen.getByLabelText('Unidad de cobro'), 'usuario')
    await user.click(screen.getByRole('button', { name: 'Guardar partida' }))

    await vi.waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Guardar partida' })).not.toBeInTheDocument(),
    )
    expect(postedBody).toMatchObject({ concept: 'Soporte', billing_unit: 'usuario' })
  })

  it('submits a delete request with the expected_version for the removed item', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/tco-preview$/, () => ({
      status: 200,
      body: {
        base_currency: 'MXN',
        horizon_years: 1,
        by_year: {},
        by_year_with_tax: {},
        by_category: {},
        grand_total: '0.00',
        grand_total_with_tax: '0.00',
      },
    }))
    let deleteUrl: URL | null = null
    router.on('DELETE', /\/cost-items\/item-1$/, ({ url }) => {
      deleteUrl = url
      return { status: 200, body: buildProposal({ version: 2, cost_items: [] }) }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel(buildProposal({ version: 3, cost_items: [buildCostItem()] }))
    await screen.findByText('Licencias anuales')

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))

    await vi.waitFor(() => expect(deleteUrl).not.toBeNull())
    expect(deleteUrl!.searchParams.get('expected_version')).toBe('3')
  })

  it('hides add/remove controls once the proposal is submitted', async () => {
    renderPanel(buildProposal({ status: 'submitted', cost_items: [buildCostItem()] }), true)

    expect(await screen.findByText('Licencias anuales')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Agregar partida de costo' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
  })
})
