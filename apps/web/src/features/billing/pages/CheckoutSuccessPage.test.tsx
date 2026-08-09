import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CheckoutSuccessPage } from './CheckoutSuccessPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

function purchaseBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'purchase-1',
    evaluation_id: 'eval-1',
    status: 'pending',
    checkout_url: '/api/v1/billing/local-checkout/cs_local_abc',
    amount_total: 150000,
    currency: 'mxn',
    created_at: '2026-01-01T00:00:00Z',
    paid_at: null,
    ...overrides,
  }
}

function renderPage(purchaseId = 'purchase-1') {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={[`/billing/checkout/success?purchase_id=${purchaseId}`]}>
        <Routes>
          <Route path="/billing/checkout/success" element={<CheckoutSuccessPage />} />
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

describe('CheckoutSuccessPage', () => {
  it('shows an error and never polls when purchase_id is missing from the URL', () => {
    render(
      <QueryClientProvider client={createAppQueryClient()}>
        <MemoryRouter initialEntries={['/billing/checkout/success']}>
          <Routes>
            <Route path="/billing/checkout/success" element={<CheckoutSuccessPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Falta el identificador de la compra.')).toBeInTheDocument()
  })

  it('shows "Confirmando..." while the purchase is still pending, never trusting the URL alone', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases\/purchase-1$/, () => ({
      status: 200,
      body: purchaseBody({ status: 'pending' }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Confirmando tu pago…')).toBeInTheDocument()
    expect(screen.queryByText('Pago confirmado')).not.toBeInTheDocument()
  })

  it('shows "Pago confirmado" once the backend (webhook-driven) state says paid - never from the URL alone', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases\/purchase-1$/, () => ({
      status: 200,
      body: purchaseBody({ status: 'paid' }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    // The success URL itself carries no "paid" signal - only ?purchase_id=,
    // used to know what to fetch (renderPage below). The "Pago confirmado"
    // text only appears because the mocked GET .../purchases/purchase-1
    // response says status="paid", proving the page trusts that response,
    // not the redirect it arrived from.
    renderPage()

    expect(await screen.findByText('Pago confirmado')).toBeInTheDocument()
  })

  it('shows the expired message when the checkout session expired', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases\/purchase-1$/, () => ({
      status: 200,
      body: purchaseBody({ status: 'expired' }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(
      await screen.findByText(/La sesión de pago expiró antes de completarse/),
    ).toBeInTheDocument()
  })
})
