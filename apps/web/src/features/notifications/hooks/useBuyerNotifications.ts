import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListNotificationsAsBuyerApiV1NotificationsGetQueryKey,
  useListNotificationsAsBuyerApiV1NotificationsGet,
  useMarkAllReadAsBuyerApiV1NotificationsReadAllPatch,
  useMarkReadAsBuyerApiV1NotificationsNotificationIdReadPatch,
  type NotificationListResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { useNotificationsPolling } from '@/features/notifications/hooks/useNotificationsPolling'

export function useBuyerNotifications() {
  const queryClient = useQueryClient()
  const listQuery = useListNotificationsAsBuyerApiV1NotificationsGet()
  const markReadMutation = useMarkReadAsBuyerApiV1NotificationsNotificationIdReadPatch()
  const markAllReadMutation = useMarkAllReadAsBuyerApiV1NotificationsReadAllPatch()

  useNotificationsPolling(async () => {
    await listQuery.refetch()
  })

  const invalidate = useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: getListNotificationsAsBuyerApiV1NotificationsGetQueryKey(),
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
