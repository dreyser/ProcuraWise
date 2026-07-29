import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AnswerField } from './AnswerField'
import type { VendorRequirementResponse } from '@/api/client'

function requirement(overrides: Partial<VendorRequirementResponse>): VendorRequirementResponse {
  return {
    id: 'req-1',
    dimension: 'functional',
    category: 'Core',
    title: 'Gestión de flujos',
    description: 'Debe soportar flujos configurables',
    priority: 'important',
    response_type: 'text',
    required: true,
    buyer_guidance: null,
    display_order: 1,
    options: null,
    ...overrides,
  }
}

describe('AnswerField - compliant_status', () => {
  it('renders the 3 real compliance options, translated, and commits the wire value on selection', async () => {
    const onCommit = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerField
        requirement={requirement({ response_type: 'compliant_status' })}
        value={null}
        vendorComment={null}
        onCommit={onCommit}
        disabled={false}
        readOnly={false}
      />,
    )

    expect(screen.getByLabelText('Cumple', { exact: true })).toBeInTheDocument()
    expect(screen.getByLabelText('Cumple parcialmente')).toBeInTheDocument()
    expect(screen.getByLabelText('No cumple')).toBeInTheDocument()

    await user.click(screen.getByLabelText('No cumple'))

    expect(onCommit).toHaveBeenCalledWith('non_compliant', undefined)
  })
})

describe('AnswerField - single_choice', () => {
  it('offers only the requirement.options as choices', async () => {
    const onCommit = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerField
        requirement={requirement({
          response_type: 'single_choice',
          options: ['SaaS', 'On-premise'],
        })}
        value={null}
        vendorComment={null}
        onCommit={onCommit}
        disabled={false}
        readOnly={false}
      />,
    )

    await user.click(screen.getByLabelText('SaaS'))
    expect(onCommit).toHaveBeenCalledWith('SaaS', undefined)
  })
})

describe('AnswerField - percentage', () => {
  it('rejects an out-of-range value client-side instead of committing it', async () => {
    const onCommit = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerField
        requirement={requirement({ response_type: 'percentage' })}
        value={null}
        vendorComment={null}
        onCommit={onCommit}
        disabled={false}
        readOnly={false}
      />,
    )

    const input = screen.getByRole('spinbutton')
    await user.type(input, '150')
    await user.tab()

    expect(onCommit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/entre 0 y 100/)
  })

  it('commits a valid percentage on blur', async () => {
    const onCommit = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerField
        requirement={requirement({ response_type: 'percentage' })}
        value={null}
        vendorComment={null}
        onCommit={onCommit}
        disabled={false}
        readOnly={false}
      />,
    )

    await user.type(screen.getByRole('spinbutton'), '75')
    await user.tab()

    expect(onCommit).toHaveBeenCalledWith(75, undefined)
  })
})

describe('AnswerField - currency', () => {
  it('serializes {amount, currency_code} matching the exact backend shape', async () => {
    const onCommit = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerField
        requirement={requirement({ response_type: 'currency' })}
        value={null}
        vendorComment={null}
        onCommit={onCommit}
        disabled={false}
        readOnly={false}
      />,
    )

    await user.type(screen.getByRole('spinbutton'), '1500')
    await user.tab()

    expect(onCommit).toHaveBeenCalledWith({ amount: 1500, currency_code: 'MXN' }, undefined)
  })
})

describe('AnswerField - read-only mode', () => {
  it('never renders an input and shows the formatted value plus the comment', () => {
    render(
      <AnswerField
        requirement={requirement({ response_type: 'compliant_status' })}
        value="partially_compliant"
        vendorComment="Pendiente de certificación"
        onCommit={() => {}}
        disabled
        readOnly
      />,
    )

    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByText('Cumple parcialmente')).toBeInTheDocument()
    expect(screen.getByText(/Pendiente de certificación/)).toBeInTheDocument()
  })

  it('shows an explicit empty state instead of a blank field when unanswered', () => {
    render(
      <AnswerField
        requirement={requirement({ response_type: 'text' })}
        value={null}
        vendorComment={null}
        onCommit={() => {}}
        disabled
        readOnly
      />,
    )
    expect(screen.getByText('Sin responder')).toBeInTheDocument()
  })
})
