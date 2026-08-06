import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReportsPage } from './ReportsPage'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

let mockRole = 'evaluation_owner'
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ actor: { role: mockRole, membership_id: 'owner-1' } }),
}))

function evaluationBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'eval-1',
    name: 'RFP con reportes',
    description: '',
    status: 'completed',
    requirements: [],
    linked_vendor_count: 1,
    created_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-02T00:00:00Z',
    approval_status: 'approved',
    approver_membership_id: 'approver-1',
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: 'eval-1',
    ...overrides,
  }
}

function readinessBody(overrides: Record<string, unknown> = {}) {
  return {
    can_generate: true,
    reasons: [],
    valid_formats: ['pdf', 'docx'],
    ...overrides,
  }
}

function reportBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'report-1',
    evaluation_id: 'eval-1',
    report_type: 'rfp_document',
    format: 'pdf',
    status: 'queued',
    requested_by_membership_id: 'owner-1',
    requested_at: '2026-01-03T00:00:00Z',
    started_at: null,
    completed_at: null,
    error: null,
    size_bytes: null,
    ...overrides,
  }
}

function renderPage() {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <MemoryRouter initialEntries={['/evaluations/eval-1/reports']}>
        <Routes>
          <Route path="/evaluations/:evaluationId/reports" element={<ReportsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockRole = 'evaluation_owner'
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ReportsPage', () => {
  it('shows an empty state and disables generation when readiness says no', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/reports\/readiness/, () => ({
      status: 200,
      body: readinessBody({ can_generate: false, reasons: ['la decisión debe estar aprobada'] }),
    }))
    router.on('GET', /\/reports$/, () => ({ status: 200, body: [] }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Sin reportes')).toBeInTheDocument()
    expect(screen.getByText('la decisión debe estar aprobada')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generar' })).toBeDisabled()
  })

  it('lets the owner trigger a report and see it listed once succeeded', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/reports\/readiness/, () => ({ status: 200, body: readinessBody() }))
    router.on('GET', /\/reports$/, () => ({ status: 200, body: [] }))
    router.on('POST', /\/reports$/, () => ({ status: 201, body: reportBody() }))
    router.on('GET', /\/reports\/report-1$/, () => ({
      status: 200,
      body: reportBody({ status: 'succeeded', size_bytes: 2048 }),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: 'Generar' })
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Generar' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Generar' }))

    expect(
      await screen.findByText('Reporte generado. Descárgalo desde la lista de abajo.'),
    ).toBeInTheDocument()
  })

  it('requests a fresh SAS URL when downloading a succeeded report', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/reports\/readiness/, () => ({ status: 200, body: readinessBody() }))
    router.on('GET', /\/reports$/, () => ({
      status: 200,
      body: [reportBody({ status: 'succeeded', size_bytes: 2048 })],
    }))
    router.on('GET', /\/reports\/report-1\/download-url$/, () => ({
      status: 200,
      body: { url: 'https://blob.example/report-1?sig=xyz', expires_at: '2026-01-03T00:15:00Z' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Descargar' }))

    await vi.waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith(
        'https://blob.example/report-1?sig=xyz',
        '_blank',
        'noopener,noreferrer',
      ),
    )
  })

  it('never shows the generation section to a non-owner buyer role', async () => {
    mockRole = 'evaluator_functional'
    const router = createFetchRouter()
    router.on('GET', /\/evaluations\/eval-1$/, () => ({ status: 200, body: evaluationBody() }))
    router.on('GET', /\/reports$/, () => ({ status: 200, body: [] }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPage()

    expect(await screen.findByText('Sin reportes')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generar' })).not.toBeInTheDocument()
  })
})
