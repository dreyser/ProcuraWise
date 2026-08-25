import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RequirementForm } from './RequirementForm'

describe('RequirementForm', () => {
  it('submits a plain (non-choice) requirement without an options key', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <RequirementForm
        defaultDimension="functional"
        nextDisplayOrder={1}
        onSubmit={onSubmit}
        onCancel={() => {}}
        isSubmitting={false}
        submitError={undefined}
      />,
    )

    await user.type(screen.getByLabelText('Categoría'), 'Core')
    await user.type(screen.getByLabelText('Título'), 'Gestión de flujos')
    await user.type(screen.getByLabelText('Descripción'), 'Debe soportar flujos configurables')
    // UAT-02 (R4): "Peso (%)" is a percentage of the dimension's point
    // budget now - 100% of "functional" (40 points) submits weight: 40.
    await user.clear(screen.getByLabelText('Peso (%)'))
    await user.type(screen.getByLabelText('Peso (%)'), '100')
    await user.click(screen.getByRole('button', { name: 'Guardar requerimiento' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const payload = onSubmit.mock.calls[0][0]
    expect(payload).toMatchObject({
      dimension: 'functional',
      category: 'Core',
      title: 'Gestión de flujos',
      description: 'Debe soportar flujos configurables',
      response_type: 'text',
      weight: 40,
      options: undefined,
    })
  })

  it('converts weight percent against the technical budget (20 points) rather than functional', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <RequirementForm
        defaultDimension="technical"
        nextDisplayOrder={1}
        onSubmit={onSubmit}
        onCancel={() => {}}
        isSubmitting={false}
        submitError={undefined}
      />,
    )

    await user.type(screen.getByLabelText('Categoría'), 'Core')
    await user.type(screen.getByLabelText('Título'), 'Disponibilidad')
    await user.type(screen.getByLabelText('Descripción'), 'SLA de disponibilidad')
    await user.clear(screen.getByLabelText('Peso (%)'))
    await user.type(screen.getByLabelText('Peso (%)'), '50')
    await user.click(screen.getByRole('button', { name: 'Guardar requerimiento' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    // 50% of the technical budget (20 points) = 10 points, not 20.
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ dimension: 'technical', weight: 10 })
  })

  it('blocks submit with an inline error when single_choice has no options, mirroring the backend rule', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <RequirementForm
        defaultDimension="functional"
        nextDisplayOrder={1}
        onSubmit={onSubmit}
        onCancel={() => {}}
        isSubmitting={false}
        submitError={undefined}
      />,
    )

    await user.type(screen.getByLabelText('Categoría'), 'Core')
    await user.type(screen.getByLabelText('Título'), 'Modelo de despliegue')
    await user.type(screen.getByLabelText('Descripción'), 'Como se despliega la solución')
    await user.selectOptions(screen.getByLabelText('Tipo de respuesta'), 'single_choice')
    await user.click(screen.getByRole('button', { name: 'Guardar requerimiento' }))

    expect(await screen.findByText(/Agrega al menos una opción/)).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits single_choice options as a plain string array once at least one is added', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <RequirementForm
        defaultDimension="functional"
        nextDisplayOrder={1}
        onSubmit={onSubmit}
        onCancel={() => {}}
        isSubmitting={false}
        submitError={undefined}
      />,
    )

    await user.type(screen.getByLabelText('Categoría'), 'Core')
    await user.type(screen.getByLabelText('Título'), 'Modelo de despliegue')
    await user.type(screen.getByLabelText('Descripción'), 'Como se despliega la solución')
    await user.selectOptions(screen.getByLabelText('Tipo de respuesta'), 'single_choice')
    await user.click(screen.getByRole('button', { name: 'Agregar opción' }))
    const optionInputs = screen
      .getAllByRole('textbox')
      .filter((el) => el !== screen.getByLabelText('Categoría'))
    await user.type(optionInputs[optionInputs.length - 1], 'SaaS')
    await user.click(screen.getByRole('button', { name: 'Guardar requerimiento' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0].options).toEqual(['SaaS'])
  })

  it('calls onCancel without submitting', async () => {
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    const user = userEvent.setup()
    render(
      <RequirementForm
        defaultDimension="technical"
        nextDisplayOrder={2}
        onSubmit={onSubmit}
        onCancel={onCancel}
        isSubmitting={false}
        submitError={undefined}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
