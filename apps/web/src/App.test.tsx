import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('redirects an anonymous session to the dev actor selector', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => [],
      }) as unknown as typeof fetch,
    )

    render(<App />)

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /selecciona un actor/i })).toBeInTheDocument(),
    )
  })

  it('shows an explanatory state when the dev selector is unavailable (404)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'not found' }),
      }) as unknown as typeof fetch,
    )

    render(<App />)

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /selector de identidad de desarrollo no disponible/i }),
      ).toBeInTheDocument(),
    )
  })
})
