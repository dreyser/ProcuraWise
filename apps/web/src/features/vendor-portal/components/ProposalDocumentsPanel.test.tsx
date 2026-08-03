import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProposalDocumentsPanel } from './ProposalDocumentsPanel'
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
    filename: 'brochure.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    uploaded_by_membership_id: 'm-1',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPanel(disabled = false) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ProposalDocumentsPanel proposalId="proposal-1" disabled={disabled} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProposalDocumentsPanel', () => {
  it('shows an empty state when there are no general attachments', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Sin documentos')).toBeInTheDocument()
  })

  it('only lists current, requirement_id=null documents (not superseded or per-requirement ones)', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: {
        items: [
          buildDocument({ id: 'doc-general', filename: 'general.pdf' }),
          buildDocument({ id: 'doc-superseded', filename: 'old.pdf', status: 'superseded' }),
          buildDocument({ id: 'doc-scoped', filename: 'scoped.pdf', requirement_id: 'req-1' }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('general.pdf')).toBeInTheDocument()
    expect(screen.queryByText('old.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('scoped.pdf')).not.toBeInTheDocument()
    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument()
    expect(screen.getByText(/v1/)).toBeInTheDocument()
  })

  it('uploads a file and refreshes the list', async () => {
    const router = createFetchRouter()
    let uploaded = false
    router.on('POST', /\/documents$/, () => {
      uploaded = true
      return { status: 201, body: buildDocument({ id: 'doc-new', filename: 'new.pdf' }) }
    })
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: { items: uploaded ? [buildDocument({ id: 'doc-new', filename: 'new.pdf' })] : [] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText('Sin documentos')).toBeInTheDocument()

    const file = new File(['%PDF-1.4 contenido'], 'new.pdf', { type: 'application/pdf' })
    const input = window.document.body.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    expect(await screen.findByText('new.pdf')).toBeInTheDocument()
  })

  it('deletes a document and removes it from the list', async () => {
    const router = createFetchRouter()
    let deleted = false
    router.on('DELETE', /\/documents\/doc-1$/, () => {
      deleted = true
      return { status: 204 }
    })
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: { items: deleted ? [] : [buildDocument()] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText('brochure.pdf')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))

    await vi.waitFor(() => expect(screen.queryByText('brochure.pdf')).not.toBeInTheDocument())
  })

  it('requests a fresh download URL and opens it on click', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [buildDocument()] } }))
    router.on('GET', /\/documents\/doc-1\/download-url$/, () => ({
      status: 200,
      body: { url: 'https://blob.example/doc-1?sig=abc', expires_at: '2026-01-01T00:15:00Z' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('brochure.pdf')

    await user.click(screen.getByRole('button', { name: 'Descargar' }))

    await vi.waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith(
        'https://blob.example/doc-1?sig=abc',
        '_blank',
        'noopener,noreferrer',
      ),
    )
  })

  it('hides upload and delete controls once the proposal is submitted, but keeps download', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [buildDocument()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel(true)
    await screen.findByText('brochure.pdf')

    expect(screen.getByRole('button', { name: 'Descargar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjuntar documento' })).not.toBeInTheDocument()
  })
})
