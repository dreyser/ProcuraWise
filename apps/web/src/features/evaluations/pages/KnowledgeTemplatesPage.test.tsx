import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { KnowledgeTemplatesPage } from './KnowledgeTemplatesPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { KnowledgeTemplateSummaryResponse } from '@/api/client'

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: 'evaluation_owner' } }),
}))

function summary(
  overrides: Partial<KnowledgeTemplateSummaryResponse> = {},
): KnowledgeTemplateSummaryResponse {
  return {
    id: 'template-1',
    name: 'Plantilla estándar',
    description: 'd',
    item_count: 2,
    created_by_membership_id: 'membership-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter>
        <KnowledgeTemplatesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('KnowledgeTemplatesPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the empty state when no templates exist', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates$/, () => ({
      status: 200,
      body: { items: [] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Todavía no hay plantillas')).toBeInTheDocument()
  })

  it('lists existing templates with their item count', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates$/, () => ({
      status: 200,
      body: { items: [summary()] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Plantilla estándar')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('creates a template and hides the form on success', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/api\/v1\/knowledge-templates$/, () => ({
      status: 200,
      body: { items: [] },
    }))
    let postBody: unknown = null
    router.on('POST', /\/api\/v1\/knowledge-templates$/, ({ body }) => {
      postBody = body
      return {
        status: 201,
        body: summary({ name: (body as { name: string }).name, item_count: 0 }),
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Nueva plantilla' }))
    await user.type(screen.getByLabelText('Nombre'), 'Plantilla nueva')
    await user.click(screen.getByRole('button', { name: 'Crear plantilla' }))

    await vi.waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Crear plantilla' })).not.toBeInTheDocument(),
    )
    expect(postBody).toMatchObject({ name: 'Plantilla nueva' })
  })
})
