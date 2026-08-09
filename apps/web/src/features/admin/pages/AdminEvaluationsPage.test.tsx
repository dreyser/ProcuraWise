import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminEvaluationsPage } from './AdminEvaluationsPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/admin/evaluations']}>
        <AdminEvaluationsPage />
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

describe('AdminEvaluationsPage', () => {
  it('never requests the cross-tenant list until a reason is submitted', () => {
    const router = createFetchRouter()
    const handler = vi.fn(() => ({ status: 200, body: { items: [], next_cursor: null } }))
    router.on('GET', /\/admin\/evaluations/, handler)
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(screen.getByLabelText('Motivo de la consulta')).toBeInTheDocument()
    expect(handler).not.toHaveBeenCalled()
  })

  it('sends the confirmed reason as a query param and renders the cross-tenant results', async () => {
    const router = createFetchRouter()
    let capturedReason: string | null = null
    router.on('GET', /\/admin\/evaluations/, (ctx) => {
      capturedReason = ctx.url.searchParams.get('reason')
      return {
        status: 200,
        body: {
          items: [
            {
              id: 'eval-1',
              tenant_id: 'tenant-1',
              tenant_name: 'Acme Compradora (dev)',
              name: 'RFP cross-tenant',
              status: 'draft',
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
          next_cursor: null,
        },
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)
    const user = userEvent.setup()

    renderPage()
    await user.type(screen.getByLabelText('Motivo de la consulta'), 'auditoria')
    await user.click(screen.getByRole('button', { name: 'Consultar' }))

    expect(await screen.findByText('Acme Compradora (dev)')).toBeInTheDocument()
    expect(screen.getByText('RFP cross-tenant')).toBeInTheDocument()
    expect(capturedReason).toBe('auditoria')
  })
})
