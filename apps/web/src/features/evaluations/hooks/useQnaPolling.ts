import { useEffect, useRef } from 'react'
import { PollingController } from '@/lib/pollingController'

// ADR 0012: 30s interval for collaborative screens (vs. 15s for job status).
const POLL_INTERVAL_MS = 30_000

/** Second real consumer of PollingController/ADR 0012 (after
 * useAiSuggestionJobStatus, Fase 13) - here it drives *when* to refresh
 * rather than owning the data itself: `refetch` is whatever React Query
 * already returned for the buyer's question list, so caching/loading/error
 * state stays entirely React Query's responsibility, while pause-on-hidden-
 * tab/backoff+jitter/offline-pause/manual-refresh semantics come from the
 * same controller every other async screen in the app already uses.
 * `isTerminal` is always false - a Q&A board is never "done" the way an AI
 * job is, it polls for as long as the page stays open. */
export function useQnaPolling(refetch: () => Promise<unknown>): void {
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
