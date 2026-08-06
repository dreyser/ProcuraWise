import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportRequirementsDialog } from './ImportRequirementsDialog'
import { createAppQueryClient } from '@/lib/queryClient'
import { createFetchRouter } from '@/testUtils/mockFetchRouter'

function renderDialog(onImported = vi.fn()) {
  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ImportRequirementsDialog
        evaluationId="eval-1"
        existingRequirementCountByDimension={{}}
        onImported={onImported}
      />
    </QueryClientProvider>,
  )
  return { onImported }
}

function previewBody() {
  return {
    columns: ['Titulo', 'Dimension', 'Categoria', 'Descripcion', 'Prioridad', 'Peso'],
    rows: [
      {
        Titulo: 'Req importado',
        Dimension: 'functional',
        Categoria: 'Core',
        Descripcion: 'Descripcion',
        Prioridad: 'important',
        Peso: 40,
      },
    ],
    suggested_mapping: {
      title: 'Titulo',
      dimension: 'Dimension',
      category: 'Categoria',
      description: 'Descripcion',
      priority: 'Prioridad',
      weight: 'Peso',
    },
  }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ImportRequirementsDialog', () => {
  it('previews a file and shows the suggested column mapping plus a data preview', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/requirements\/import\/preview$/, () => ({
      status: 200,
      body: previewBody(),
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Importar Excel/CSV' }))
    const file = new File(['Titulo\nReq importado'], 'requerimientos.csv', { type: 'text/csv' })
    const input = window.document.body.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    expect(await screen.findByText('Vista previa (1 filas)')).toBeInTheDocument()
    expect(screen.getByText('Req importado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar importación' })).toBeEnabled()
  })

  it('confirms the mapped rows as RequirementCreateRequest and closes on success', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/requirements\/import\/preview$/, () => ({
      status: 200,
      body: previewBody(),
    }))
    let confirmedBody: unknown
    router.on('POST', /\/requirements\/import\/confirm$/, async (ctx) => {
      confirmedBody = ctx.body
      return {
        status: 201,
        body: {
          requirements: [
            {
              id: 'req-1',
              dimension: 'functional',
              category: 'Core',
              title: 'Req importado',
              description: 'Descripcion',
              priority: 'important',
              response_type: 'text',
              weight: 40,
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
    const { onImported } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Importar Excel/CSV' }))
    const file = new File(['Titulo\nReq importado'], 'requerimientos.csv', { type: 'text/csv' })
    const input = window.document.body.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)
    await screen.findByRole('button', { name: 'Confirmar importación' })

    await user.click(screen.getByRole('button', { name: 'Confirmar importación' }))

    await vi.waitFor(() =>
      expect(confirmedBody).toEqual({
        requirements: [
          {
            dimension: 'functional',
            category: 'Core',
            title: 'Req importado',
            description: 'Descripcion',
            priority: 'important',
            response_type: 'text',
            weight: 40,
            required: false,
            display_order: 1,
            buyer_guidance: null,
          },
        ],
      }),
    )
    await vi.waitFor(() => expect(onImported).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('disables confirmation until every required column is mapped', async () => {
    const router = createFetchRouter()
    router.on('POST', /\/requirements\/import\/preview$/, () => ({
      status: 200,
      body: {
        columns: ['Titulo'],
        rows: [{ Titulo: 'Req sin dimension' }],
        suggested_mapping: { title: 'Titulo' },
      },
    }))
    vi.stubGlobal('fetch', router.fetchImpl)

    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Importar Excel/CSV' }))
    const file = new File(['Titulo\nReq sin dimension'], 'r.csv', { type: 'text/csv' })
    const input = window.document.body.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    await screen.findByText('Vista previa (1 filas)')
    expect(screen.getByRole('button', { name: 'Confirmar importación' })).toBeDisabled()
    expect(
      screen.getByText('Mapea todas las columnas obligatorias (*) para continuar.'),
    ).toBeInTheDocument()
  })
})
