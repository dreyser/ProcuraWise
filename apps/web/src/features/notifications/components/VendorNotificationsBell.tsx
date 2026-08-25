import { useVendorNotifications } from '@/features/notifications/hooks/useVendorNotifications'
import { NotificationsBell } from '@/features/notifications/components/NotificationsBell'

export function VendorNotificationsBell() {
  const { items, unreadCount, isLoading, markRead, markAllRead } = useVendorNotifications()

  return (
    <NotificationsBell
      items={items}
      unreadCount={unreadCount}
      isLoading={isLoading}
      audience="vendor"
      onMarkRead={(notificationId) => void markRead(notificationId)}
      onMarkAllRead={() => void markAllRead()}
    />
  )
}
