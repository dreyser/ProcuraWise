import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WeightSummary } from './WeightSummary'

// UAT-02 (R4): displayed in percent of the dimension's point budget, not
// raw points - the underlying exactness check still happens in points.
describe('WeightSummary', () => {
  it('shows 100%/100% with no warning when functional weights hit the 40-point target', () => {
    render(<WeightSummary dimension="functional" currentWeight={40} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Funcional: 100% / 100%')
    expect(status).not.toHaveTextContent('excede')
    expect(status).not.toHaveTextContent('faltan')
  })

  it('warns in percent when technical weights are under the 20-point target', () => {
    render(<WeightSummary dimension="technical" currentWeight={15} />)
    // 15/20 = 75%, 25% short of the 20-point target.
    expect(screen.getByRole('status')).toHaveTextContent('Técnico: 75% / 100%')
    expect(screen.getByRole('status')).toHaveTextContent('faltan 25% para el objetivo')
  })

  it('warns in percent when weights exceed the target', () => {
    render(<WeightSummary dimension="functional" currentWeight={45} />)
    // 45/40 = 112.5%, 12.5% over the 40-point target.
    expect(screen.getByRole('status')).toHaveTextContent('Funcional: 112.5% / 100%')
    expect(screen.getByRole('status')).toHaveTextContent('excede el objetivo por 12.5%')
  })
})
