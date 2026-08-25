import { useBuyerNotifications } from '@/features/notifications/hooks/useBuyerNotifications'
import { NotificationsBell } from '@/features/notifications/components/NotificationsBell'

export function BuyerNotificationsBell() {
  const { items, unreadCount, isLoading, markRead, markAllRead } = useBuyerNotifications()

  return (
    <NotificationsBell
      items={items}
      unreadCount={unreadCount}
      isLoading={isLoading}
      audience="buyer"
      onMarkRead={(notificationId) => void markRead(notificationId)}
      onMarkAllRead={() => void markAllRead()}
    />
  )
}
