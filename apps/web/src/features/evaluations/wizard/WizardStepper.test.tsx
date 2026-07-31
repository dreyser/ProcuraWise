import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { WizardStepper } from './WizardStepper'

describe('WizardStepper', () => {
  it('marks the current step and disables everything past maxReachableStep', () => {
    render(<WizardStepper currentStep={2} maxReachableStep={2} onStepSelect={() => {}} />)

    expect(screen.getByRole('button', { name: '2. Requerimientos' })).toHaveAttribute(
      'aria-current',
      'step',
    )
    expect(screen.getByRole('button', { name: '1. Datos generales' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '2. Requerimientos' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '3. Proveedores' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '4. Revisión e inicio' })).toBeDisabled()
  })

  it('calls onStepSelect only for a reachable step', async () => {
    const onStepSelect = vi.fn()
    const user = userEvent.setup()
    render(<WizardStepper currentStep={3} maxReachableStep={3} onStepSelect={onStepSelect} />)

    await user.click(screen.getByRole('button', { name: '1. Datos generales' }))
    expect(onStepSelect).toHaveBeenCalledWith(1)

    onStepSelect.mockClear()
    await user.click(screen.getByRole('button', { name: '4. Revisión e inicio' }))
    expect(onStepSelect).not.toHaveBeenCalled()
  })
})
