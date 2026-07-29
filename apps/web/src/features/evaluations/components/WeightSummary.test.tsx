import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WeightSummary } from './WeightSummary'

describe('WeightSummary', () => {
  it('shows the exact target with no warning when functional weights sum to 40', () => {
    render(<WeightSummary dimension="functional" currentWeight={40} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Funcional: 40 / 40 puntos')
    expect(status).not.toHaveTextContent('excede')
    expect(status).not.toHaveTextContent('faltan')
  })

  it('warns when technical weights are under the 20-point target', () => {
    render(<WeightSummary dimension="technical" currentWeight={15} />)
    expect(screen.getByRole('status')).toHaveTextContent('faltan 5 para el objetivo')
  })

  it('warns when weights exceed the target', () => {
    render(<WeightSummary dimension="functional" currentWeight={45} />)
    expect(screen.getByRole('status')).toHaveTextContent('excede el objetivo por 5')
  })
})
