import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ScoreInput } from './ScoreInput'

describe('ScoreInput', () => {
  it('renders exactly the 6 valid values (0-5), matching the backend range', () => {
    render(<ScoreInput requirementId="req-1" value={null} onChange={() => {}} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.getAttribute('value'))).toEqual(['0', '1', '2', '3', '4', '5'])
  })

  it('marks the current value as checked', () => {
    render(<ScoreInput requirementId="req-1" value={3} onChange={() => {}} />)
    expect(screen.getByRole('radio', { name: '3' })).toBeChecked()
  })

  it('calls onChange with the numeric score when a value is picked', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ScoreInput requirementId="req-1" value={null} onChange={onChange} />)

    await user.click(screen.getByRole('radio', { name: '5' }))

    expect(onChange).toHaveBeenCalledWith(5)
  })

  it('disables every option when disabled', () => {
    render(<ScoreInput requirementId="req-1" value={null} onChange={() => {}} disabled />)
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled()
    }
  })
})
