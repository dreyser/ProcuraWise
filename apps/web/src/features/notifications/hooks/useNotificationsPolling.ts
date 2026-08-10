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

/** Fase 26 (Hardening): the controller is built inside `useEffect` (empty
 * deps - constructed once for the component's lifetime, matching the
 * original render-time-guard behavior), not during render - see
 * useReportJobStatus.ts/usePurchaseStatus.ts for the full rationale
 * (`react-hooks/refs`). `refetchRef` keeps calling whichever `refetch` is
 * current without needing the effect to re-run (every caller passes a
 * fresh inline closure on every render, so keying the effect on `refetch`
 * would restart the poll interval on every unrelated re-render) - synced
 * from its own dependency-less effect, not by writing to it during render
 * (also disallowed now). */
export function useNotificationsPolling(refetch: () => Promise<unknown>): void {
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
