import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('is not rendered when closed', () => {
    render(
      <ConfirmDialog
        open={false}
        onOpenChange={() => {}}
        title="Enviar propuesta"
        description="Una vez enviada no podrás editarla."
        confirmLabel="Enviar"
        onConfirm={() => {}}
      />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the title, description, and calls onConfirm when confirmed', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Enviar propuesta"
        description="Una vez enviada no podrás editarla."
        confirmLabel="Enviar"
        onConfirm={onConfirm}
      />,
    )

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAccessibleName('Enviar propuesta')
    expect(screen.getByText('Una vez enviada no podrás editarla.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onOpenChange(false) when cancelled, without calling onConfirm', async () => {
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Eliminar requerimiento"
        description="Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={onConfirm}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('disables both actions and shows a processing label while pending', () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Enviar propuesta"
        description="…"
        confirmLabel="Enviar"
        onConfirm={() => {}}
        isPending
      />,
    )

    expect(screen.getByRole('button', { name: 'Procesando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
  })
})
