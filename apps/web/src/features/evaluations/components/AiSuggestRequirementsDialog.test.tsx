import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AiSuggestRequirementsDialog } from './AiSuggestRequirementsDialog'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { AIRequirementCandidate } from '@/api/client'

function candidate(overrides: Partial<AIRequirementCandidate> = {}): AIRequirementCandidate {
  return {
    dimension: 'functional',
    category: 'Reporting',
    title: 'Custom dashboards',
    description: 'Configurable dashboards for KPIs',
    priority: 'important',
    response_type: 'text',
    weight: 5,
    required: false,
    buyer_guidance: '',
    options: [],
    rationale: 'Matches the described reporting need',
    sources: [],
    ...overrides,
  }
}

function renderDialog(onAccepted = vi.fn()) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <AiSuggestRequirementsDialog evaluationId="eval-1" onAccepted={onAccepted} />
    </QueryClientProvider>,
  )
  return { onAccepted }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AiSuggestRequirementsDialog', () => {
  it('triggers a job, shows the returned candidate, and accepts it', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/ai\/requirement-suggestions$/, () => ({
      status: 202,
      body: {
        job_id: 'job-1',
        status_url: '/api/v1/evaluations/eval-1/ai/requirement-suggestions/job-1',
      },
    }))
    router.on('GET', /\/ai\/requirement-suggestions\/job-1$/, () => ({
      status: 200,
      body: {
        job_id: 'job-1',
        status: 'succeeded',
        candidates: [candidate()],
        error: null,
        model: 'gpt-4o-mini',
        prompt_version: 'v1',
        token_usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        cost_estimate: null,
        latency_ms: 500,
        accepted_requirement_ids: [],
      },
    }))
    let acceptedIndices: number[] | undefined
    router.on('POST', /\/ai\/requirement-suggestions\/job-1\/accept$/, async (ctx) => {
      acceptedIndices = (ctx.body as { candidate_indices: number[] }).candidate_indices
      return {
        status: 201,
        body: {
          added_requirements: [
            {
              id: 'req-1',
              dimension: 'functional',
              category: 'Reporting',
              title: 'Custom dashboards',
              description: 'Configurable dashboards for KPIs',
              priority: 'important',
              response_type: 'text',
              weight: 5,
              required: false,
              buyer_guidance: null,
              display_order: 1,
              options: null,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ],
        },
      }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    const { onAccepted } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))
    await user.type(
      screen.getByLabelText('¿Qué necesitas comprar?'),
      'Necesitamos una herramienta de reportes',
    )
    await user.click(screen.getByRole('button', { name: 'Generar sugerencias' }))

    expect(await screen.findByText('Custom dashboards')).toBeInTheDocument()
    expect(screen.getByText('Matches the described reporting need')).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Aceptar seleccionados (1)' }))

    await vi.waitFor(() => expect(acceptedIndices).toEqual([0]))
    await vi.waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows an error banner when triggering the job fails', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/ai\/requirement-suggestions$/, () => ({
      status: 409,
      body: { detail: 'evaluation is not draft' },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))
    await user.type(screen.getByLabelText('¿Qué necesitas comprar?'), 'algo')
    await user.click(screen.getByRole('button', { name: 'Generar sugerencias' }))

    expect(
      await screen.findByText(
        'Los datos cambiaron desde la última vez que los consultaste. Recarga para continuar.',
      ),
    ).toBeInTheDocument()
  })

  it('shows a failed-job message with a retry action', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/ai\/requirement-suggestions$/, () => ({
      status: 202,
      body: { job_id: 'job-2', status_url: '/x' },
    }))
    router.on('GET', /\/ai\/requirement-suggestions\/job-2$/, () => ({
      status: 200,
      body: {
        job_id: 'job-2',
        status: 'failed',
        candidates: null,
        error: 'Azure OpenAI is not configured',
        model: null,
        prompt_version: 'v1',
        token_usage: null,
        cost_estimate: null,
        latency_ms: null,
        accepted_requirement_ids: [],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))
    await user.type(screen.getByLabelText('¿Qué necesitas comprar?'), 'algo')
    await user.click(screen.getByRole('button', { name: 'Generar sugerencias' }))

    expect(await screen.findByText('Azure OpenAI is not configured')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })

  it('renders citations resolved from source_catalog and a degradation warning banner', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/ai\/requirement-suggestions$/, () => ({
      status: 202,
      body: { job_id: 'job-3', status_url: '/x' },
    }))
    router.on('GET', /\/ai\/requirement-suggestions\/job-3$/, () => ({
      status: 200,
      body: {
        job_id: 'job-3',
        status: 'succeeded',
        candidates: [
          candidate({ sources: ['src-1', 'src-unknown'] }),
          candidate({ title: 'Uncited candidate', sources: [] }),
        ],
        error: null,
        model: 'gpt-4o-mini',
        prompt_version: 'v2',
        token_usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        cost_estimate: null,
        latency_ms: 500,
        accepted_requirement_ids: [],
        source_catalog: [
          {
            source_type: 'curated_source',
            source_id: 'src-1',
            title: 'Gartner ERP guide',
            url: 'https://example.com/erp-guide',
            retrieved_at: '2026-08-01T00:00:00Z',
          },
        ],
        warnings: [
          {
            code: 'research_provider_unavailable',
            source_type: 'web_search',
            message: 'no disponible',
          },
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Sugerir con IA' }))
    await user.type(screen.getByLabelText('¿Qué necesitas comprar?'), 'algo')
    await user.click(screen.getByRole('button', { name: 'Generar sugerencias' }))

    // A valid, resolvable source_id renders as a link to the catalog entry.
    const citation = await screen.findByRole('link', { name: 'Gartner ERP guide' })
    expect(citation).toHaveAttribute('href', 'https://example.com/erp-guide')
    // An unknown/invented source_id (not in source_catalog) never renders -
    // founder decision, Fase 14 planning: URLs shown to users always come
    // from the persisted catalog, never directly from model output.
    expect(screen.queryByText('src-unknown')).not.toBeInTheDocument()
    // A candidate with no sources at all shows no "Fuentes:" line.
    expect(screen.getByText('Uncited candidate')).toBeInTheDocument()

    expect(
      screen.getByText(
        'Algunas fuentes de investigación no estuvieron disponibles para esta consulta; se usaron únicamente las fuentes restantes.',
      ),
    ).toBeInTheDocument()
  })
})
