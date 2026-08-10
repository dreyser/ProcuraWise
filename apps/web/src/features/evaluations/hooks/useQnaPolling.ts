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
 * job is, it polls for as long as the page stays open.
 *
 * Fase 26 (Hardening): the controller is built inside `useEffect`, not
 * during render - see useReportJobStatus.ts/usePurchaseStatus.ts for the
 * full rationale (eslint-plugin-react-hooks 7's `react-hooks/refs`). The
 * effect itself runs once (empty deps, matching the original's "construct
 * once for the component's lifetime" behavior) rather than being keyed on
 * `refetch` - every caller (QnaPage.tsx) passes a fresh inline closure on
 * every render, so keying on it would tear down and rebuild the
 * controller (restarting the poll interval) on every unrelated re-render.
 * `refetchRef` keeps calling whichever `refetch` is current without
 * needing the effect to re-run - the ref is synced from its own
 * dependency-less effect (runs after every commit), not by writing to it
 * directly during render - `react-hooks/refs` (Fase 26) disallows *any*
 * ref mutation during render now, including the previously-common
 * "update every render" idiom. */
export function useQnaPolling(refetch: () => Promise<unknown>): void {
  const refetchRef = useRef(refetch)
  useEffect(() => {
    refetchRef.current = refetch
  })

  useEffect(() => {
    const controller = new PollingController<null>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal: () => false,
      fetchFn: async () => {
        await refetchRef.current()
        return null
      },
    })
    controller.start()
    return () => controller.dispose()
  }, [])
}
