import { useEffect, useRef } from 'react'
import { PollingController } from '@/lib/pollingController'

// ADR 0012: 30s interval for collaborative screens (vs. 15s for job status) -
// same cadence and same non-terminal shape as
// features/evaluations/hooks/useQnaPolling.ts, this phase's second
// unrelated consumer of that exact pattern (Fase 24 plan S5.5): the
// notification bell never "finishes" polling either, so `isTerminal` stays
// permanently false and `refetch` (React Query's own) remains the sole
// owner of the actual list/unread-count state.
const POLL_INTERVAL_MS = 30_000

export function useNotificationsPolling(refetch: () => Promise<unknown>): void {
  const controllerRef = useRef<PollingController<null> | null>(null)

  if (!controllerRef.current) {
    const controller = new PollingController<null>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal: () => false,
      fetchFn: async () => {
        await refetch()
        return null
      },
    })
    controllerRef.current = controller
    controller.start()
  }

  useEffect(() => {
    return () => {
      controllerRef.current?.dispose()
      controllerRef.current = null
    }
  }, [])
}
