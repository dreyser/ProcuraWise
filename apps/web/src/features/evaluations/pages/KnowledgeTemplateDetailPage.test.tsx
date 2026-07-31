import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { KnowledgeTemplateDetailPage } from './KnowledgeTemplateDetailPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { KnowledgeTemplateDetailResponse } from '@/api/client'

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: 'evaluation_owner' } }),
}))

function detail(
  overrides: Partial<KnowledgeTemplateDetailResponse> = {},
): KnowledgeTemplateDetailResponse {
  return {
    id: 'template-1',
    name: 'Plantilla estándar',
    description: 'Descripción',
    items: [],
    created_by_membership_id: 'membership-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/knowledge-templates/template-1']}>
        <Routes>
          <Route path="/knowledge-templates" element={<p>Lista de plantillas</p>} />
          <Route
            path="/knowledge-templates/:templateId"
            element={<KnowledgeTemplateDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('KnowledgeTemplateDetailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the template name and description', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates\/template-1$/, () => ({
      status: 200,
      body: detail(),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Plantilla estándar')).toBeInTheDocument()
    expect(screen.getByText('Descripción')).toBeInTheDocument()
  })

  it('shows an unavailable message on 404', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates\/template-1$/, () => ({ status: 404 }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Esta plantilla no está disponible.')).toBeInTheDocument()
  })

  it('lists items grouped by dimension', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates\/template-1$/, () => ({
      status: 200,
      body: detail({
        items: [
          {
            id: 'item-1',
            dimension: 'functional',
            category: 'Core',
            title: 'Requerimiento 1',
            description: 'd',
            priority: 'important',
            response_type: 'text',
            weight: 10,
            required: true,
            buyer_guidance: null,
            display_order: 1,
            options: null,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Requerimiento 1')).toBeInTheDocument()
  })

  it('deletes the template and calls the delete endpoint', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates\/template-1$/, () => ({
      status: 200,
      body: detail(),
    }))
    let deleteCalled = false
    router.on('DELETE', /\/api\/v1\/knowledge-templates\/template-1$/, () => {
      deleteCalled = true
      return { status: 204 }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Eliminar plantilla' }))
    await user.click(screen.getByRole('button', { name: 'Eliminar' }))

    await vi.waitFor(() => expect(deleteCalled).toBe(true))
    expect(await screen.findByText('Lista de plantillas')).toBeInTheDocument()
  })
})
