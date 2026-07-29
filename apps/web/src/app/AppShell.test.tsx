import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'
import * as ActorContextModule from '@/actor/ActorContext'
import type { ActorContextResponse } from '@/api/client'

function actor(overrides: Partial<ActorContextResponse>): ActorContextResponse {
  return {
    membership_id: 'm-1',
    user_id: 'u-1',
    tenant_id: 't-1',
    tenant_name: 'Acme Compradora (dev)',
    role: 'evaluation_owner',
    vendor_org_id: null,
    display_name: 'Owner A',
    ...overrides,
  }
}

function renderWithActor(overrides: Partial<ActorContextResponse>) {
  const clearActor = vi.fn()
  vi.spyOn(ActorContextModule, 'useActor').mockReturnValue({
    actor: actor(overrides),
    status: 'ready',
    selectActor: vi.fn(),
    clearActor,
  })
  render(
    <MemoryRouter>
      <AppShell>
        <p>contenido de la página</p>
      </AppShell>
    </MemoryRouter>,
  )
  return { clearActor }
}

describe('AppShell - role-aware navigation', () => {
  it('shows only the buyer nav for evaluation_owner, never the vendor portal link', () => {
    renderWithActor({ role: 'evaluation_owner' })
    expect(screen.getByRole('link', { name: 'Evaluaciones' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mis propuestas' })).not.toBeInTheDocument()
  })

  it('shows only the buyer nav for evaluator too', () => {
    renderWithActor({ role: 'evaluator', display_name: 'Evaluator A' })
    expect(screen.getByRole('link', { name: 'Evaluaciones' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mis propuestas' })).not.toBeInTheDocument()
  })

  it('shows only the vendor nav for vendor_contact, never a buyer link', () => {
    renderWithActor({
      role: 'vendor_contact',
      display_name: 'Vendor Contact A',
      vendor_org_id: 'vendor-1',
    })
    expect(screen.getByRole('link', { name: 'Mis propuestas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Evaluaciones' })).not.toBeInTheDocument()
  })

  it('always shows the active actor (tenant, name, role) and the dev-mode banner', () => {
    renderWithActor({ role: 'evaluation_owner' })
    expect(screen.getByText(/Acme Compradora \(dev\)/)).toBeInTheDocument()
    expect(screen.getByText(/Owner A/)).toBeInTheDocument()
    expect(screen.getByText(/Responsable de evaluación/)).toBeInTheDocument()
    expect(screen.getByText(/Modo de desarrollo/)).toBeInTheDocument()
  })

  it('clears the actor when "Cambiar de actor" is used', async () => {
    const user = userEvent.setup()
    const { clearActor } = renderWithActor({ role: 'evaluation_owner' })

    await user.click(screen.getByRole('button', { name: 'Cambiar de actor' }))

    expect(clearActor).toHaveBeenCalledTimes(1)
  })
})
