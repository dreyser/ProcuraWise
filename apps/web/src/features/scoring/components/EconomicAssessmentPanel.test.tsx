import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EconomicAssessmentPanel } from './EconomicAssessmentPanel'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

const COMMERCIAL_KEYS = [
  'payment_terms',
  'price_protection',
  'contractual_flexibility',
  'discounts_incentives',
  'billing_transparency',
]
const RISK_KEYS = [
  'variable_cost_exposure',
  'increases_indexation',
  'assumptions_exclusions',
  'fx_fiscal_regulatory',
  'exit_portability_lockin',
]

function assessmentBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 'assessment-1',
    evaluation_id: 'eval-1',
    proposal_id: 'proposal-1',
    commercial_scores: COMMERCIAL_KEYS.map((key) => ({
      criterion_key: key,
      score: 4,
      comment: null,
    })),
    risk_scores: RISK_KEYS.map((key) => ({ criterion_key: key, score: 4, comment: null })),
    version: 1,
    created_by_membership_id: 'owner-1',
    updated_by_membership_id: 'owner-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPanel(isEditable = true) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <EconomicAssessmentPanel
        evaluationId="eval-1"
        proposalId="proposal-1"
        isEditable={isEditable}
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

describe('EconomicAssessmentPanel', () => {
  it('renders all 10 fixed criteria with an empty draft when no assessment exists yet', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({
      status: 404,
      body: { detail: 'Not Found' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Pago y plazo')).toBeInTheDocument()
    for (const key of [...COMMERCIAL_KEYS, ...RISK_KEYS]) {
      expect(screen.getByRole('radio', { name: `${labelFor(key)}: N/A` })).not.toBeChecked()
    }
    expect(screen.getByRole('button', { name: 'Guardar evaluación económica' })).toBeEnabled()
  })

  it('hydrates existing scores/comments from the last saved assessment', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({ status: 200, body: assessmentBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByRole('radio', { name: 'Pago y plazo: 4' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Exposición cambiaria y fiscal: 4' })).toBeChecked()
  })

  it('blocks saving with a client-side error when a criterion is left unset', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({
      status: 404,
      body: { detail: 'Not Found' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Pago y plazo')

    await user.click(screen.getByRole('button', { name: 'Guardar evaluación económica' }))

    expect(await screen.findByText(/Completa los 10 criterios/)).toBeInTheDocument()
  })

  it('blocks saving with a client-side error when an extreme score has no comment', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({
      status: 404,
      body: { detail: 'Not Found' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Pago y plazo')

    for (const key of [...COMMERCIAL_KEYS, ...RISK_KEYS]) {
      await user.click(screen.getByRole('radio', { name: `${labelFor(key)}: 3` }))
    }
    // Make the first criterion extreme (0) without filling its comment.
    await user.click(screen.getByRole('radio', { name: 'Pago y plazo: 0' }))
    await user.click(screen.getByRole('button', { name: 'Guardar evaluación económica' }))

    expect(await screen.findByText(/Falta comentario obligatorio/)).toBeInTheDocument()
  })

  it('saves the full 10-criterion assessment when every rule is satisfied', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({
      status: 404,
      body: { detail: 'Not Found' },
    }))
    let capturedBody: Record<string, unknown> | undefined
    router.on('PUT', /\/economic-assessment$/, async (ctx) => {
      capturedBody = ctx.body as Record<string, unknown>
      return { status: 200, body: assessmentBody({ version: 1 }) }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Pago y plazo')

    for (const key of [...COMMERCIAL_KEYS, ...RISK_KEYS]) {
      await user.click(screen.getByRole('radio', { name: `${labelFor(key)}: 3` }))
    }
    await user.click(screen.getByRole('button', { name: 'Guardar evaluación económica' }))

    await vi.waitFor(() => expect(capturedBody).toBeDefined())
    expect(capturedBody?.commercial_scores).toHaveLength(5)
    expect(capturedBody?.risk_scores).toHaveLength(5)
    expect(
      (capturedBody?.commercial_scores as Array<{ score: number }>).every((s) => s.score === 3),
    ).toBe(true)
  })

  it('disables every input and hides the save button when not editable', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/economic-assessment$/, () => ({ status: 200, body: assessmentBody() }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel(false)

    await screen.findByText('Pago y plazo')
    expect(
      screen.queryByRole('button', { name: 'Guardar evaluación económica' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Pago y plazo: 4' })).toBeDisabled()
  })
})

const LABELS: Record<string, string> = {
  payment_terms: 'Pago y plazo',
  price_protection: 'Protección de precio',
  contractual_flexibility: 'Flexibilidad contractual',
  discounts_incentives: 'Descuentos e incentivos',
  billing_transparency: 'Transparencia y facturación',
  variable_cost_exposure: 'Exposición a costos variables',
  increases_indexation: 'Incrementos e indexación',
  assumptions_exclusions: 'Supuestos y exclusiones',
  fx_fiscal_regulatory: 'Exposición cambiaria y fiscal',
  exit_portability_lockin: 'Salida y portabilidad',
}

function labelFor(key: string): string {
  return LABELS[key]
}
