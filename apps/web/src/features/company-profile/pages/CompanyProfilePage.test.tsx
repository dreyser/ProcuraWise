import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CompanyProfilePage } from './CompanyProfilePage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

function profileBody(overrides: Record<string, unknown> = {}) {
  return {
    legal_name: '',
    tax_id: '',
    address: '',
    industry: '',
    website_url: '',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/company-profile']}>
        <CompanyProfilePage />
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

// UAT-03 (R4): tenant_admin-only company profile settings form.
describe('CompanyProfilePage', () => {
  it('renders empty fields before any profile has been saved', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/company-profile$/, () => ({ status: 200, body: profileBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByLabelText('Razón social')).toHaveValue('')
    expect(screen.getByLabelText('Sitio web')).toHaveValue('')
  })

  it('prefills the form with the existing profile', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/company-profile$/, () => ({
      status: 200,
      body: profileBody({
        legal_name: 'Acme Compras SA de CV',
        website_url: 'https://acme.example.com',
      }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByLabelText('Razón social')).toHaveValue('Acme Compras SA de CV')
    expect(screen.getByLabelText('Sitio web')).toHaveValue('https://acme.example.com')
  })

  it('saves the edited fields via PUT and reflects the response', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/company-profile$/, () => ({ status: 200, body: profileBody() }))
    let capturedBody: Record<string, unknown> | undefined
    router.on('PUT', /\/company-profile$/, async (ctx) => {
      capturedBody = ctx.body as Record<string, unknown>
      return { status: 200, body: profileBody(capturedBody) }
    })
    vi.stubGlobal('fetch', router.fetchImpl)
    const user = userEvent.setup()

    renderPage()
    await screen.findByLabelText('Razón social')

    await user.type(screen.getByLabelText('Razón social'), 'Acme Compras SA de CV')
    await user.type(screen.getByLabelText('Sitio web'), 'https://acme.example.com')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await vi.waitFor(() => expect(capturedBody?.legal_name).toBe('Acme Compras SA de CV'))
    expect(capturedBody?.website_url).toBe('https://acme.example.com')
    expect(await screen.findByLabelText('Razón social')).toHaveValue('Acme Compras SA de CV')
  })

  it('shows a banner when the update is rejected', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/company-profile$/, () => ({ status: 200, body: profileBody() }))
    router.on('PUT', /\/company-profile$/, () => ({
      status: 422,
      body: { detail: [{ loc: ['body', 'website_url'], msg: 'invalid', type: 'value_error' }] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const user = userEvent.setup()

    renderPage()
    await screen.findByLabelText('Razón social')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
