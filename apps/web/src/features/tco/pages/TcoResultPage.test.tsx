import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TcoResultPage } from './TcoResultPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/proposals/proposal-1/tco']}>
        <Routes>
          <Route
            path="/evaluations/:evaluationId/proposals/:proposalId/tco"
            element={<TcoResultPage />}
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

describe('TcoResultPage', () => {
  it('renders the year breakdown, category breakdown, and frozen fx rates', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/tco$/, () => ({
      status: 200,
      body: {
        base_currency: 'MXN',
        horizon_years: 2,
        by_year: { '1': '18500.00', '2': '18500.00' },
        by_year_with_tax: { '1': '21460.00', '2': '21460.00' },
        by_category: { initial: '5000.00', recurring: '32000.00' },
        grand_total: '37000.00',
        grand_total_with_tax: '42920.00',
        fx_rates_used: [
          {
            from_currency: 'USD',
            to_currency: 'MXN',
            rate: '18.50',
            effective_date: '2026-01-01',
            source: 'manual',
          },
        ],
        calculated_at: '2026-08-04T00:00:00Z',
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText(/TCO \(2 año\(s\), MXN\)/)).toBeInTheDocument()
    expect(screen.getAllByText('18500.00')).toHaveLength(2)
    expect(screen.getByText('37000.00')).toBeInTheDocument()
    expect(screen.getByText('42920.00')).toBeInTheDocument()
    expect(screen.getByText(/USD → MXN: 18.50/)).toBeInTheDocument()
  })

  it('shows a not-available message when the proposal has not been submitted yet', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/tco$/, () => ({ status: 404 }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(
      await screen.findByText(/aún no está disponible \(la propuesta debe estar enviada\)/),
    ).toBeInTheDocument()
  })
})
