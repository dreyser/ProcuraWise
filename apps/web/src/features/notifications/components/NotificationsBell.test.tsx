import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { type NotificationResponse } from '@/api/client'
import { NotificationsBell } from './NotificationsBell'

function LocationMarker() {
  const location = useLocation()
  return <p>Landed: {location.pathname}</p>
}

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

// UAT-13 (R4): clicking a notification navigates now, so useNavigate()
// requires a Router in every render - a landing marker route lets tests
// assert which page a click actually lands on.
function renderBell(
  props: Omit<Parameters<typeof NotificationsBell>[0], 'audience'> & {
    audience?: Parameters<typeof NotificationsBell>[0]['audience']
  },
) {
  return render(
    <MemoryRouter initialEntries={['/start']}>
      <Routes>
        <Route path="/start" element={<NotificationsBell audience="buyer" {...props} />} />
        <Route path="*" element={<LocationMarker />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('NotificationsBell', () => {
  it('shows no unread badge and an empty-state message when there are no notifications', async () => {
    const user = userEvent.setup()
    renderBell({
      items: [],
      unreadCount: 0,
      isLoading: false,
      onMarkRead: vi.fn(),
      onMarkAllRead: vi.fn(),
    })

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
    renderBell({
      items,
      unreadCount: 1,
      isLoading: false,
      onMarkRead: vi.fn(),
      onMarkAllRead: vi.fn(),
    })

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
      notification({ id: 'unread-1', read_at: null, event: 'qna_answer_published' }),
      notification({
        id: 'read-1',
        read_at: '2026-08-02T00:00:00Z',
        event: 'qna_answer_published',
      }),
    ]
    renderBell({
      items,
      unreadCount: 1,
      isLoading: false,
      onMarkRead,
      onMarkAllRead: vi.fn(),
    })

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
    renderBell({
      items: [notification({ event: 'qna_answer_published' })],
      unreadCount: 1,
      isLoading: false,
      onMarkRead: vi.fn(),
      onMarkAllRead,
    })

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    await user.click(await screen.findByText('Marcar todas'))
    expect(onMarkAllRead).toHaveBeenCalledTimes(1)
  })

  it('navigates to the resolved target when a linkable notification is clicked (UAT-13)', async () => {
    const user = userEvent.setup()
    renderBell({
      items: [notification({ event: 'evaluation_published', evaluation_id: 'eval-42' })],
      unreadCount: 1,
      isLoading: false,
      onMarkRead: vi.fn(),
      onMarkAllRead: vi.fn(),
    })

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    await user.click(await screen.findByText('RFP Notificaciones fue publicada'))

    expect(await screen.findByText('Landed: /evaluations/eval-42')).toBeInTheDocument()
  })

  it('does not navigate for a non-linkable notification (e.g. vendor_invited)', async () => {
    const user = userEvent.setup()
    renderBell({
      items: [notification({ event: 'vendor_invited', evaluation_id: null })],
      unreadCount: 1,
      isLoading: false,
      onMarkRead: vi.fn(),
      onMarkAllRead: vi.fn(),
    })

    await user.click(screen.getByRole('button', { name: 'Notificaciones (1 sin leer)' }))
    await user.click(await screen.findByText('RFP Notificaciones fue publicada'))

    expect(screen.queryByText(/Landed:/)).not.toBeInTheDocument()
  })
})
