import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RequirementQuestionThread } from './RequirementQuestionThread'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { VendorQuestionResponse } from '@/api/client'

function buildQuestion(overrides: Partial<VendorQuestionResponse> = {}): VendorQuestionResponse {
  return {
    id: 'q-1',
    proposal_id: 'proposal-1',
    requirement_id: 'req-1',
    scope: 'requirement',
    body: 'Soportan SSO?',
    status: 'open',
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    current_answer: null,
    answer_history: [],
    ...overrides,
  }
}

function renderWidget(disabled = false) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <RequirementQuestionThread
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

describe('RequirementQuestionThread', () => {
  it('shows an empty state when there are no questions for this requirement', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget()

    expect(await screen.findByText('Sin preguntas todavía.')).toBeInTheDocument()
  })

  it('only shows questions scoped to this requirement, ignoring general/other ones', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: {
        items: [
          buildQuestion(),
          buildQuestion({ id: 'q-other', requirement_id: 'req-2', body: 'Otro requerimiento' }),
          buildQuestion({
            id: 'q-general',
            requirement_id: null,
            scope: 'general',
            body: 'General',
          }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget()

    expect(await screen.findByText('Soportan SSO?')).toBeInTheDocument()
    expect(screen.queryByText('Otro requerimiento')).not.toBeInTheDocument()
    expect(screen.queryByText('General')).not.toBeInTheDocument()
  })

  it('creates a question scoped to this requirement', async () => {
    const router = createFetchRouter()
    let created = false
    router.on('POST', /\/questions$/, () => {
      created = true
      return { status: 201, body: buildQuestion({ id: 'q-new', body: 'Nueva pregunta' }) }
    })
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: { items: created ? [buildQuestion({ id: 'q-new', body: 'Nueva pregunta' })] : [] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderWidget()
    await screen.findByText('Sin preguntas todavía.')

    await user.type(
      screen.getByPlaceholderText('Pregunta sobre este requerimiento…'),
      'Nueva pregunta',
    )
    await user.click(screen.getByRole('button', { name: 'Preguntar' }))

    expect(await screen.findByText('Nueva pregunta')).toBeInTheDocument()
  })

  it('hides ask/withdraw controls once the proposal is submitted', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [buildQuestion()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderWidget(true)
    await screen.findByText('Soportan SSO?')

    expect(screen.queryByRole('button', { name: 'Preguntar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retirar' })).not.toBeInTheDocument()
  })
})
