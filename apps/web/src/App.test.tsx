import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the ProcuraWise heading', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }) as unknown as typeof fetch)

    render(<App />)

    expect(screen.getByRole('heading', { name: /procurawise/i })).toBeInTheDocument()
  })
})
