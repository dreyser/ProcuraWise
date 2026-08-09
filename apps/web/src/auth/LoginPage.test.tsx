import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'
import { AuthProvider } from './AuthContext'
import { createAppQueryClient } from '@/lib/queryClient'

function renderLoginPage() {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/evaluations" element={<p>Página de evaluaciones</p>} />
            <Route path="/billing" element={<p>Página de facturación</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

describe('LoginPage', () => {
  it('shows inline validation errors and never calls the backend for an empty form', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    renderLoginPage()
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('El correo es obligatorio')).toBeInTheDocument()
    expect(screen.getByText('La contraseña es obligatoria')).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('rejects a malformed email before submitting', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn())

    renderLoginPage()
    await user.type(screen.getByLabelText('Correo'), 'not-an-email')
    await user.type(screen.getByLabelText('Contraseña'), 'whatever')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('Correo inválido')).toBeInTheDocument()
  })

  it('shows a generic error banner on wrong credentials, without leaking the backend detail', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'invalid credentials' })),
    )

    renderLoginPage()
    await user.type(screen.getByLabelText('Correo'), 'owner.a@dev.procurawise.local')
    await user.type(screen.getByLabelText('Contraseña'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Correo o contraseña incorrectos.')
    expect(alert).not.toHaveTextContent('invalid credentials')
  })

  it('logs in and navigates to the buyer home on a single-membership account', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/auth/login')) {
        return jsonResponse(200, {
          pre_session_token: 'pre-1',
          token_type: 'bearer',
          expires_in: 300,
        })
      }
      if (url.includes('/auth/memberships')) {
        return jsonResponse(200, {
          memberships: [
            {
              membership_id: 'm-1',
              tenant_id: 't-1',
              tenant_name: 'Acme',
              role: 'evaluation_owner',
              display_name: 'Owner A',
            },
          ],
        })
      }
      if (url.includes('/auth/switch-tenant')) {
        return jsonResponse(200, {
          access_token: 'access-1',
          token_type: 'bearer',
          expires_in: 1800,
          actor: {
            membership_id: 'm-1',
            user_id: 'u-1',
            tenant_id: 't-1',
            tenant_name: 'Acme',
            role: 'evaluation_owner',
            vendor_org_id: null,
            display_name: 'Owner A',
          },
        })
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderLoginPage()
    await user.type(screen.getByLabelText('Correo'), 'owner.a@dev.procurawise.local')
    await user.type(screen.getByLabelText('Contraseña'), 'dev-password-2026')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(screen.getByText('Página de evaluaciones')).toBeInTheDocument())
  })

  it('regression (Fase 25): a tenant_admin single-membership login lands on /billing, not /evaluations', async () => {
    // Bug found while E2E-testing Bloque 5: the single-membership fast path
    // used to hardcode roleHomePath('evaluation_owner') regardless of the
    // actor's real role - harmless before Fase 25 (every buyer role shared
    // /evaluations), but tenant_admin now has its own home and has no
    // access to /evaluations at all (backend 403s it too).
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/auth/login')) {
        return jsonResponse(200, {
          pre_session_token: 'pre-1',
          token_type: 'bearer',
          expires_in: 300,
        })
      }
      if (url.includes('/auth/memberships')) {
        return jsonResponse(200, {
          memberships: [
            {
              membership_id: 'm-1',
              tenant_id: 't-1',
              tenant_name: 'Acme',
              role: 'tenant_admin',
              display_name: 'Tenant Admin A',
            },
          ],
        })
      }
      if (url.includes('/auth/switch-tenant')) {
        return jsonResponse(200, {
          access_token: 'access-1',
          token_type: 'bearer',
          expires_in: 1800,
          actor: {
            membership_id: 'm-1',
            user_id: 'u-1',
            tenant_id: 't-1',
            tenant_name: 'Acme',
            role: 'tenant_admin',
            vendor_org_id: null,
            display_name: 'Tenant Admin A',
          },
        })
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderLoginPage()
    await user.type(screen.getByLabelText('Correo'), 'tenant-admin.a@dev.procurawise.local')
    await user.type(screen.getByLabelText('Contraseña'), 'dev-password-2026')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(screen.getByText('Página de facturación')).toBeInTheDocument())
  })

  describe('OIDC buttons', () => {
    const originalLocation = window.location

    beforeEach(() => {
      Object.defineProperty(window, 'location', {
        value: { ...originalLocation, href: '' },
        writable: true,
        configurable: true,
      })
    })

    afterEach(() => {
      Object.defineProperty(window, 'location', {
        value: originalLocation,
        writable: true,
        configurable: true,
      })
    })

    it('redirects the whole page to the Microsoft OIDC login endpoint', async () => {
      const user = userEvent.setup()
      renderLoginPage()

      await user.click(screen.getByRole('button', { name: 'Continuar con Microsoft' }))

      expect(window.location.href).toBe('/api/v1/auth/oidc/microsoft/login')
    })

    it('redirects the whole page to the Google OIDC login endpoint', async () => {
      const user = userEvent.setup()
      renderLoginPage()

      await user.click(screen.getByRole('button', { name: 'Continuar con Google' }))

      expect(window.location.href).toBe('/api/v1/auth/oidc/google/login')
    })
  })
})
