import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListNotificationsAsVendorApiV1VendorPortalNotificationsGetQueryKey,
  useListNotificationsAsVendorApiV1VendorPortalNotificationsGet,
  useMarkAllReadAsVendorApiV1VendorPortalNotificationsReadAllPatch,
  useMarkReadAsVendorApiV1VendorPortalNotificationsNotificationIdReadPatch,
  type NotificationListResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { useNotificationsPolling } from '@/features/notifications/hooks/useNotificationsPolling'

export function useVendorNotifications() {
  const queryClient = useQueryClient()
  const listQuery = useListNotificationsAsVendorApiV1VendorPortalNotificationsGet()
  const markReadMutation =
    useMarkReadAsVendorApiV1VendorPortalNotificationsNotificationIdReadPatch()
  const markAllReadMutation = useMarkAllReadAsVendorApiV1VendorPortalNotificationsReadAllPatch()

  useNotificationsPolling(async () => {
    await listQuery.refetch()
  })

  const invalidate = useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: getListNotificationsAsVendorApiV1VendorPortalNotificationsGetQueryKey(),
      }),
    [queryClient],
  )

  const markRead = useCallback(
    async (notificationId: string) => {
      await markReadMutation.mutateAsync({ notificationId })
      await invalidate()
    },
    [markReadMutation, invalidate],
  )

  const markAllRead = useCallback(async () => {
    await markAllReadMutation.mutateAsync()
    await invalidate()
  }, [markAllReadMutation, invalidate])

  const data = unwrapData<NotificationListResponse>(listQuery.data)

  return {
    items: data?.items ?? [],
    unreadCount: data?.unread_count ?? 0,
    isLoading: listQuery.isLoading,
    error: listQuery.error,
    markRead,
    markAllRead,
  }
}
