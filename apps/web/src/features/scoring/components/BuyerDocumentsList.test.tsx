import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuyerDocumentsList } from './BuyerDocumentsList'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { DocumentResponse } from '@/api/client'

function buildDocument(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: 'doc-1',
    proposal_id: 'proposal-1',
    requirement_id: null,
    version: 1,
    status: 'current',
    filename: 'evidencia.pdf',
    content_type: 'application/pdf',
    size_bytes: 4096,
    uploaded_by_membership_id: 'm-vendor',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderList() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <BuyerDocumentsList evaluationId="eval-1" proposalId="proposal-1" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BuyerDocumentsList', () => {
  it('shows an empty state when the vendor attached nothing', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderList()

    expect(await screen.findByText('Sin documentos')).toBeInTheDocument()
  })

  it('lists only current documents, never a superseded version', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: {
        items: [
          buildDocument({ id: 'doc-current', filename: 'v2.pdf' }),
          buildDocument({ id: 'doc-old', filename: 'v1.pdf', status: 'superseded' }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderList()

    expect(await screen.findByText('v2.pdf')).toBeInTheDocument()
    expect(screen.queryByText('v1.pdf')).not.toBeInTheDocument()
  })

  it('never renders an upload or delete control - the buyer router has none', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [buildDocument()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderList()
    await screen.findByText('evidencia.pdf')

    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /adjuntar/i })).not.toBeInTheDocument()
    expect(window.document.body.querySelector('input[type="file"]')).not.toBeInTheDocument()
  })

  it('requests a fresh download URL on click', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [buildDocument()] } }))
    router.on('GET', /\/documents\/doc-1\/download-url$/, () => ({
      status: 200,
      body: { url: 'https://blob.example/doc-1?sig=xyz', expires_at: '2026-01-01T00:15:00Z' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    const user = userEvent.setup()
    renderList()
    await screen.findByText('evidencia.pdf')

    await user.click(screen.getByRole('button', { name: 'Descargar' }))

    await vi.waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith(
        'https://blob.example/doc-1?sig=xyz',
        '_blank',
        'noopener,noreferrer',
      ),
    )
  })
})
