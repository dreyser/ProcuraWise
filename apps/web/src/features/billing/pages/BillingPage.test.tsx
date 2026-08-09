import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BillingPage } from './BillingPage'
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

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/billing']}>
        <BillingPage />
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

describe('BillingPage', () => {
  it('shows an empty state when the tenant has no purchases yet', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Sin compras')).toBeInTheDocument()
  })

  it('lists existing purchases with translated status and formatted amount', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases$/, () => ({
      status: 200,
      body: { items: [purchaseBody({ status: 'paid', paid_at: '2026-01-02T00:00:00Z' })] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('eval-1')).toBeInTheDocument()
    expect(screen.getByText('Pagada')).toBeInTheDocument()
    expect(screen.getByText('$1,500.00')).toBeInTheDocument()
  })

  it('the Pagar button stays disabled until an evaluation id is entered', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const user = userEvent.setup()

    renderPage()
    await screen.findByText('Sin compras')

    expect(screen.getByRole('button', { name: 'Pagar' })).toBeDisabled()
    await user.type(screen.getByLabelText('ID de la evaluación'), 'eval-2')
    expect(screen.getByRole('button', { name: 'Pagar' })).toBeEnabled()
  })

  it('creating a checkout session redirects the whole page to the returned checkout_url', async () => {
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      value: { ...originalLocation, href: '' },
      writable: true,
      configurable: true,
    })

    const router = createFetchRouter()
    router.on('GET', /\/billing\/purchases$/, () => ({ status: 200, body: { items: [] } }))
    router.on('POST', /\/billing\/checkout-sessions$/, () => ({
      status: 201,
      body: purchaseBody(),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const user = userEvent.setup()

    renderPage()
    await screen.findByText('Sin compras')
    await user.type(screen.getByLabelText('ID de la evaluación'), 'eval-1')
    await user.click(screen.getByRole('button', { name: 'Pagar' }))

    await vi.waitFor(() =>
      expect(window.location.href).toBe('/api/v1/billing/local-checkout/cs_local_abc'),
    )

    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
      configurable: true,
    })
  })
})
