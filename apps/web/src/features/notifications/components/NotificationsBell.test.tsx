import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { type NotificationResponse } from '@/api/client'
import { NotificationsBell } from './NotificationsBell'

function notification(overrides: Partial<NotificationResponse> = {}): NotificationResponse {
  return {
    id: 'notif-1',
    event: 'evaluation_published',
    resource_type: 'evaluation',
    resource_id: 'eval-1',
    evaluation_id: 'eval-1',
    title: 'RFP Notificaciones fue publicada',
    body: 'La evaluación ya está lista para recibir propuestas.',
    created_at: '2026-08-01T00:00:00Z',
    read_at: null,
    ...overrides,
  }
}

describe('NotificationsBell', () => {
  it('shows no unread badge and an empty-state message when there are no notifications', async () => {
    const user = userEvent.setup()
    render(
      <NotificationsBell
        items={[]}
        unreadCount={0}
        isLoading={false}
        onMarkRead={vi.fn()}
        onMarkAllRead={vi.fn()}
      />,
    )

    expect(screen.queryByText('0')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Notificaciones' }))
    expect(await screen.findByText('No tienes notificaciones')).toBeInTheDocument()
  })

  it('shows the unread count badge and each item translated, with an unread marker', async () => {
    const user = userEvent.setup()
    const items = [
      notification({ id: 'notif-1', event: 'evaluation_published', read_at: null }),
      notification({
        id: 'notif-2',
        event: 'qna_answer_published',
        read_at: '2026-08-02T00:00:00Z',
      }),
    ]
    render(
      <NotificationsBell
        items={items}
        unreadCount={1}
        isLoading={false}
        onMarkRead={vi.fn()}
        onMarkAllRead={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' })).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    expect(await screen.findByText('Evaluación publicada')).toBeInTheDocument()
    expect(screen.getByText('Respuesta publicada')).toBeInTheDocument()
    expect(screen.getByText('Marcar todas')).toBeInTheDocument()
  })

  it('marks a single unread item as read when clicked, but never a read one', async () => {
    const user = userEvent.setup()
    const onMarkRead = vi.fn()
    const items = [
      notification({ id: 'unread-1', read_at: null }),
      notification({ id: 'read-1', read_at: '2026-08-02T00:00:00Z' }),
    ]
    render(
      <NotificationsBell
        items={items}
        unreadCount={1}
        isLoading={false}
        onMarkRead={onMarkRead}
        onMarkAllRead={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    const [unreadItem, readItem] = await screen.findAllByText('RFP Notificaciones fue publicada')

    await user.click(unreadItem)
    expect(onMarkRead).toHaveBeenCalledWith('unread-1')

    // onSelect calls preventDefault so the menu stays open (no need to
    // reopen it) - clicking the already-read item must be a no-op.
    onMarkRead.mockClear()
    await user.click(readItem)
    expect(onMarkRead).not.toHaveBeenCalled()
  })

  it('calls onMarkAllRead when "Marcar todas" is clicked', async () => {
    const user = userEvent.setup()
    const onMarkAllRead = vi.fn()
    render(
      <NotificationsBell
        items={[notification()]}
        unreadCount={1}
        isLoading={false}
        onMarkRead={vi.fn()}
        onMarkAllRead={onMarkAllRead}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    await user.click(await screen.findByText('Marcar todas'))
    expect(onMarkAllRead).toHaveBeenCalledTimes(1)
  })
})
