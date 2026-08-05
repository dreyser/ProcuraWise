import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReopenProposalDialog } from './ReopenProposalDialog'

describe('ReopenProposalDialog', () => {
  it('is not rendered when closed', () => {
    render(
      <ReopenProposalDialog
        open={false}
        onOpenChange={() => {}}
        vendorName="Acme Corp"
        onConfirm={() => {}}
      />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the vendor name and keeps the confirm button disabled until both fields are filled', async () => {
    const user = userEvent.setup()
    render(
      <ReopenProposalDialog
        open
        onOpenChange={() => {}}
        vendorName="Acme Corp"
        onConfirm={() => {}}
      />,
    )

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAccessibleName('Reabrir propuesta de Acme Corp')
    const confirmButton = screen.getByRole('button', { name: 'Reabrir propuesta' })
    expect(confirmButton).toBeDisabled()

    await user.type(screen.getByLabelText('Motivo'), 'Negociación de precio')
    expect(confirmButton).toBeDisabled()

    await user.type(screen.getByLabelText('Nueva fecha límite de respuesta'), '2030-06-01')
    expect(confirmButton).toBeEnabled()
  })

  it('calls onConfirm with the trimmed reason and an ISO deadline', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <ReopenProposalDialog
        open
        onOpenChange={() => {}}
        vendorName="Acme Corp"
        onConfirm={onConfirm}
      />,
    )

    await user.type(screen.getByLabelText('Motivo'), '  Negociación de precio  ')
    await user.type(screen.getByLabelText('Nueva fecha límite de respuesta'), '2030-06-01')
    await user.click(screen.getByRole('button', { name: 'Reabrir propuesta' }))

    expect(onConfirm).toHaveBeenCalledWith({
      reason: 'Negociación de precio',
      response_deadline: '2030-06-01T00:00:00.000Z',
    })
  })

  it('calls onOpenChange(false) and resets the form when cancelled', async () => {
    const onOpenChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ReopenProposalDialog
        open
        onOpenChange={onOpenChange}
        vendorName="Acme Corp"
        onConfirm={() => {}}
      />,
    )

    await user.type(screen.getByLabelText('Motivo'), 'Negociación de precio')
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('disables inputs and shows a processing label while pending', () => {
    render(
      <ReopenProposalDialog
        open
        onOpenChange={() => {}}
        vendorName="Acme Corp"
        onConfirm={() => {}}
        isPending
      />,
    )

    expect(screen.getByRole('button', { name: 'Procesando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
    expect(screen.getByLabelText('Motivo')).toBeDisabled()
    expect(screen.getByLabelText('Nueva fecha límite de respuesta')).toBeDisabled()
  })
})
