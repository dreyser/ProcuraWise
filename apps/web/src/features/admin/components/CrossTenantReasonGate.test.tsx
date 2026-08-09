import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CrossTenantReasonGate } from './CrossTenantReasonGate'

describe('CrossTenantReasonGate', () => {
  it('never calls onConfirm while the reason is under 3 characters', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(<CrossTenantReasonGate confirmedReason={null} onConfirm={onConfirm} />)

    await user.type(screen.getByLabelText('Motivo de la consulta'), 'ab')
    expect(screen.getByRole('button', { name: 'Consultar' })).toBeDisabled()

    await user.type(screen.getByLabelText('Motivo de la consulta'), 'c')
    expect(screen.getByRole('button', { name: 'Consultar' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Consultar' }))
    expect(onConfirm).toHaveBeenCalledWith('abc')
  })

  it('shows no input once a reason is confirmed, and echoes it back', () => {
    render(
      <CrossTenantReasonGate confirmedReason="auditoría de cumplimiento" onConfirm={vi.fn()} />,
    )

    expect(screen.queryByLabelText('Motivo de la consulta')).not.toBeInTheDocument()
    expect(screen.getByText('auditoría de cumplimiento')).toBeInTheDocument()
  })

  it('trims leading/trailing whitespace before confirming', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(<CrossTenantReasonGate confirmedReason={null} onConfirm={onConfirm} />)

    await user.type(screen.getByLabelText('Motivo de la consulta'), '  soporte  ')
    await user.click(screen.getByRole('button', { name: 'Consultar' }))
    expect(onConfirm).toHaveBeenCalledWith('soporte')
  })
})
