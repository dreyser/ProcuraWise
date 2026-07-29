import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

function actor(overrides: Partial<{ tenant_name: string; display_name: string; role: string }>) {
  return {
    tenant_name: 'Acme Compradora (dev)',
    display_name: 'Owner A',
    role: 'evaluation_owner',
    ...overrides,
  }
}

function renderShell(
  actorOverrides: Partial<{ tenant_name: string; display_name: string; role: string }>,
  shellOverrides: Partial<{ exitLabel: string; devModeNotice: boolean }> = {},
) {
  const onExit = vi.fn()
  render(
    <MemoryRouter>
      <AppShell
        actor={actor(actorOverrides)}
        exitLabel={shellOverrides.exitLabel ?? 'Cambiar de actor'}
        devModeNotice={shellOverrides.devModeNotice ?? true}
        onExit={onExit}
      >
        <p>contenido de la página</p>
      </AppShell>
    </MemoryRouter>,
  )
  return { onExit }
}

describe('AppShell - role-aware navigation', () => {
  it('shows only the buyer nav for evaluation_owner, never the vendor portal link', () => {
    renderShell({ role: 'evaluation_owner' })
    expect(screen.getByRole('link', { name: 'Evaluaciones' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mis propuestas' })).not.toBeInTheDocument()
  })

  it('shows only the buyer nav for evaluator too', () => {
    renderShell({ role: 'evaluator', display_name: 'Evaluator A' })
    expect(screen.getByRole('link', { name: 'Evaluaciones' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mis propuestas' })).not.toBeInTheDocument()
  })

  it('shows only the vendor nav for vendor_contact, never a buyer link', () => {
    renderShell({ role: 'vendor_contact', display_name: 'Vendor Contact A' })
    expect(screen.getByRole('link', { name: 'Mis propuestas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Evaluaciones' })).not.toBeInTheDocument()
  })

  it('always shows the active actor (tenant, name, role)', () => {
    renderShell({ role: 'evaluation_owner' })
    expect(screen.getByText(/Acme Compradora \(dev\)/)).toBeInTheDocument()
    expect(screen.getByText(/Owner A/)).toBeInTheDocument()
    expect(screen.getByText(/Responsable de evaluación/)).toBeInTheDocument()
  })

  it('shows the dev-mode banner only when devModeNotice is set (vendor interim mechanism)', () => {
    renderShell({ role: 'vendor_contact' }, { devModeNotice: true })
    expect(screen.getByText(/Modo de desarrollo/)).toBeInTheDocument()
  })

  it('hides the dev-mode banner for a real buyer session', () => {
    renderShell({ role: 'evaluation_owner' }, { devModeNotice: false, exitLabel: 'Cerrar sesión' })
    expect(screen.queryByText(/Modo de desarrollo/)).not.toBeInTheDocument()
  })

  it('calls onExit when the exit action is used', async () => {
    const user = userEvent.setup()
    const { onExit } = renderShell({ role: 'evaluation_owner' })

    await user.click(screen.getByRole('button', { name: 'Cambiar de actor' }))

    expect(onExit).toHaveBeenCalledTimes(1)
  })
})
