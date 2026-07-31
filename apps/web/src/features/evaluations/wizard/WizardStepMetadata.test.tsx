import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WizardStepMetadata } from './WizardStepMetadata'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'
import type { EvaluationDetailResponse } from '@/api/client'

function evaluation(overrides: Partial<EvaluationDetailResponse> = {}): EvaluationDetailResponse {
  return {
    id: 'eval-1',
    name: 'Evaluación existente',
    description: 'Descripción existente',
    status: 'draft',
    requirements: [],
    linked_vendor_count: 0,
    created_by_membership_id: 'membership-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    collecting_responses_started_at: null,
    evaluating_started_at: null,
    completed_at: null,
    approval_status: 'not_requested',
    approver_membership_id: null,
    response_deadline: null,
    approval_requested_at: null,
    approval_requested_by_membership_id: null,
    approval_decided_at: null,
    approval_decided_by_membership_id: null,
    approval_comment: null,
    approval_snapshot_id: null,
    ...overrides,
  }
}

function renderStep(props: Partial<Parameters<typeof WizardStepMetadata>[0]> = {}) {
  const onCreated = vi.fn()
  const onNext = vi.fn()
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <WizardStepMetadata evaluation={undefined} onCreated={onCreated} onNext={onNext} {...props} />
    </QueryClientProvider>,
  )
  return { onCreated, onNext }
}

describe('WizardStepMetadata', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a new evaluation and calls onCreated, without touching PATCH', async () => {
    const router = createFetchRouter()
    let sawPatch = false
    router.on('POST', /\/api\/v1\/evaluations$/, ({ body }) => ({
      status: 201,
      body: evaluation({
        name: (body as { name: string }).name,
        description: (body as { description: string }).description,
      }),
    }))
    router.on('PATCH', /\/api\/v1\/evaluations\/[^/]+$/, () => {
      sawPatch = true
      return { status: 200, body: evaluation() }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    const { onCreated } = renderStep({ evaluation: undefined })

    await user.type(screen.getByLabelText('Nombre'), 'Mi nueva evaluación')
    await user.click(screen.getByRole('button', { name: 'Crear y continuar' }))

    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1))
    expect(onCreated.mock.calls[0][0]).toMatchObject({ name: 'Mi nueva evaluación' })
    expect(sawPatch).toBe(false)
  })

  it('advances to the next step without a PATCH call when nothing changed', async () => {
    const router = createFetchRouter()
    let patchCalls = 0
    router.on('PATCH', /\/api\/v1\/evaluations\/[^/]+$/, () => {
      patchCalls += 1
      return { status: 200, body: evaluation() }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    const existing = evaluation()
    const { onNext } = renderStep({ evaluation: existing })

    expect(screen.getByLabelText('Nombre')).toHaveValue(existing.name)
    await user.click(screen.getByRole('button', { name: 'Siguiente' }))

    await vi.waitFor(() => expect(onNext).toHaveBeenCalledTimes(1))
    expect(patchCalls).toBe(0)
  })

  it('PATCHes the change and only then advances when the name was edited', async () => {
    const router = createFetchRouter()
    let patchBody: unknown = null
    router.on('PATCH', /\/api\/v1\/evaluations\/[^/]+$/, ({ body }) => {
      patchBody = body
      return { status: 200, body: evaluation({ name: 'Nombre editado' }) }
    })
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    const existing = evaluation()
    const { onNext } = renderStep({ evaluation: existing })

    const nameInput = screen.getByLabelText('Nombre')
    await user.clear(nameInput)
    await user.type(nameInput, 'Nombre editado')
    await user.click(screen.getByRole('button', { name: 'Siguiente' }))

    await vi.waitFor(() => expect(onNext).toHaveBeenCalledTimes(1))
    expect(patchBody).toMatchObject({ name: 'Nombre editado' })
  })
})
