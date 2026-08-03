import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProposalQnaPanel } from './ProposalQnaPanel'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { PublicQuestionResponse, VendorQuestionResponse } from '@/api/client'

function buildQuestion(overrides: Partial<VendorQuestionResponse> = {}): VendorQuestionResponse {
  return {
    id: 'q-1',
    proposal_id: 'proposal-1',
    requirement_id: null,
    scope: 'general',
    body: 'Cuando cierra el RFP?',
    status: 'open',
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    current_answer: null,
    answer_history: [],
    ...overrides,
  }
}

function buildPublicQuestion(
  overrides: Partial<PublicQuestionResponse> = {},
): PublicQuestionResponse {
  return {
    id: 'q-public-1',
    requirement_id: null,
    scope: 'general',
    body: 'Otro proveedor pregunto esto',
    current_answer: {
      version: 1,
      body: 'Respuesta publica',
      visibility: 'published_anonymized',
      answered_by_membership_id: 'owner-1',
      answered_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  }
}

function renderPanel(disabled = false) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ProposalQnaPanel proposalId="proposal-1" disabled={disabled} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProposalQnaPanel', () => {
  it('shows empty states for both own and published questions', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Sin preguntas')).toBeInTheDocument()
    expect(await screen.findByText('Sin preguntas públicas')).toBeInTheDocument()
  })

  it('only lists own general questions, not requirement-scoped ones', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: {
        items: [
          buildQuestion({ id: 'q-general', body: 'Pregunta general' }),
          buildQuestion({
            id: 'q-scoped',
            body: 'Pregunta de requerimiento',
            scope: 'requirement',
            requirement_id: 'req-1',
          }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Pregunta general')).toBeInTheDocument()
    expect(screen.queryByText('Pregunta de requerimiento')).not.toBeInTheDocument()
  })

  it('creates a question and refreshes the list', async () => {
    const router = createFetchRouter()
    let created = false
    router.on('POST', /\/questions$/, () => {
      created = true
      return { status: 201, body: buildQuestion({ id: 'q-new', body: 'Nueva pregunta' }) }
    })
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: { items: created ? [buildQuestion({ id: 'q-new', body: 'Nueva pregunta' })] : [] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText('Sin preguntas')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Escribe tu pregunta…'), 'Nueva pregunta')
    await user.click(screen.getByRole('button', { name: 'Preguntar' }))

    expect(await screen.findByText('Nueva pregunta')).toBeInTheDocument()
  })

  it('withdraws an open question and removes it from the list', async () => {
    const router = createFetchRouter()
    let withdrawn = false
    router.on('DELETE', /\/questions\/q-1$/, () => {
      withdrawn = true
      return { status: 204 }
    })
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: { items: withdrawn ? [] : [buildQuestion()] },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText('Cuando cierra el RFP?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retirar' }))

    await vi.waitFor(() =>
      expect(screen.queryByText('Cuando cierra el RFP?')).not.toBeInTheDocument(),
    )
  })

  it('shows the answer body and visibility once answered', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({
      status: 200,
      body: {
        items: [
          buildQuestion({
            status: 'answered',
            current_answer: {
              version: 1,
              body: 'Cierra el 30 de agosto.',
              visibility: 'private',
              answered_by_membership_id: 'owner-1',
              answered_at: '2026-01-01T00:00:00Z',
            },
          }),
        ],
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Cierra el 30 de agosto.')).toBeInTheDocument()
    expect(screen.getByText('Privada')).toBeInTheDocument()
    expect(screen.getByText('Respondida')).toBeInTheDocument()
    // Answered questions cannot be withdrawn.
    expect(screen.queryByRole('button', { name: 'Retirar' })).not.toBeInTheDocument()
  })

  it('lists published questions from other vendors without any identity field', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions\/published$/, () => ({
      status: 200,
      body: { items: [buildPublicQuestion()] },
    }))
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel()

    expect(await screen.findByText('Otro proveedor pregunto esto')).toBeInTheDocument()
    expect(screen.getByText('Respuesta publica')).toBeInTheDocument()
  })

  it('hides the ask/withdraw controls once the proposal is submitted', async () => {
    const router = createFetchRouter()
    router.on('GET', /\/questions\/published$/, () => ({ status: 200, body: { items: [] } }))
    router.on('GET', /\/questions$/, () => ({ status: 200, body: { items: [buildQuestion()] } }))
    vi.stubGlobal('fetch', router.fetchImpl)

    renderPanel(true)
    await screen.findByText('Cuando cierra el RFP?')

    expect(screen.queryByRole('button', { name: 'Preguntar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retirar' })).not.toBeInTheDocument()
  })
})
