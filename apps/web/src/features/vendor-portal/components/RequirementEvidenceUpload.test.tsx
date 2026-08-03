import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RequirementEvidenceUpload } from './RequirementEvidenceUpload'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { DocumentResponse } from '@/api/client'

function buildDocument(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: 'doc-1',
    proposal_id: 'proposal-1',
    requirement_id: 'req-1',
    version: 1,
    status: 'current',
    filename: 'evidencia.pdf',
    content_type: 'application/pdf',
    size_bytes: 1024,
    uploaded_by_membership_id: 'm-1',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderWidget(disabled = false) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <RequirementEvidenceUpload
        proposalId="proposal-1"
        requirementId="req-1"
        disabled={disabled}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RequirementEvidenceUpload', () => {
  it('shows an explicit empty state when no evidence is attached for this requirement', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget()

    expect(await screen.findByText('Sin evidencia adjunta.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Adjuntar evidencia' })).toBeInTheDocument()
  })

  it('only shows the document scoped to this requirement, ignoring others', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: {
        items: [
          buildDocument(),
          buildDocument({ id: 'doc-other', requirement_id: 'req-2', filename: 'otro.pdf' }),
          buildDocument({ id: 'doc-general', requirement_id: null, filename: 'general.pdf' }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget()

    expect(await screen.findByText('evidencia.pdf')).toBeInTheDocument()
    expect(screen.queryByText('otro.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('general.pdf')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reemplazar evidencia' })).toBeInTheDocument()
  })

  it('uploading replaces the current evidence (new version shown after refresh)', async () => {
    const router = createFetchRouter()
    let replaced = false
    router.on('POST', /\/documents$/, () => {
      replaced = true
      return { status: 201, body: buildDocument({ id: 'doc-2', version: 2 }) }
    })
    router.on('GET', /\/documents$/, () => ({
      status: 200,
      body: { items: [replaced ? buildDocument({ id: 'doc-2', version: 2 }) : buildDocument()] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderWidget()
    await screen.findByText(/v1/)

    const file = new File(['%PDF-1.4 nueva'], 'v2.pdf', { type: 'application/pdf' })
    const input = window.document.body.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    await screen.findByText(/v2/)
  })

  it('hides upload and delete controls once submitted, but keeps download', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/documents$/, () => ({ status: 200, body: { items: [buildDocument()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget(true)
    await screen.findByText('evidencia.pdf')

    expect(screen.getByRole('button', { name: 'Descargar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /evidencia/i })).not.toBeInTheDocument()
  })
})
