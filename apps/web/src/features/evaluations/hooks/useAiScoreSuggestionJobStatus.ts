import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import {
  getScoreSuggestionStatusApiV1EvaluationsEvaluationIdProposalsProposalIdAiScoreSuggestionsJobIdGet,
  type ScoreSuggestionJobStatusResponse,
} from '@/api/client'
import { unwrapDataOrThrow } from '@/lib/http'
import { PollingController, type PollingSnapshot } from '@/lib/pollingController'

// ADR 0012: 15s interval for job status (vs. 30s for collaborative screens) -
// same as useAiSuggestionJobStatus.ts (Fase 13).
const POLL_INTERVAL_MS = 15_000

function isTerminal(result: ScoreSuggestionJobStatusResponse): boolean {
  return result.status === 'succeeded' || result.status === 'failed'
}

function snapshotsAreEqual<T>(a: PollingSnapshot<T> | null, b: PollingSnapshot<T> | null): boolean {
  if (a === b) return true
  if (a === null || b === null) return false
  return (
    a.status === b.status &&
    a.result === b.result &&
    a.error === b.error &&
    a.stale === b.stale &&
    a.lastUpdatedAt?.getTime() === b.lastUpdatedAt?.getTime()
  )
}

/** Fase 18 (ADR 0022): second real consumer of `PollingController` for a job
 * status screen.
 *
 * Fase 26 (Hardening): migrated from a manual `useState` synced via
 * `setState` calls directly in the effect body (flagged by
 * eslint-plugin-react-hooks 7's `react-hooks/set-state-in-effect` - exactly
 * the "cascading synchronous render" pattern that rule targets) to the same
 * `useSyncExternalStore` + memoized-snapshot shape as
 * `useReportJobStatus.ts`/`useAiSuggestionJobStatus.ts`. This also
 * structurally preserves the original "subscribe before start" fix this
 * hook's history is about (`getSnapshot` always reads the controller's own
 * current state directly - there is no separate subscribe-then-notify race
 * to lose an update to, unlike the old setState-based version). */
export function useAiScoreSuggestionJobStatus(
  evaluationId: string,
  proposalId: string,
  jobId: string | null,
): PollingSnapshot<ScoreSuggestionJobStatusResponse> | null {
  const controllerRef = useRef<PollingController<ScoreSuggestionJobStatusResponse> | null>(null)
  const snapshotCacheRef = useRef<PollingSnapshot<ScoreSuggestionJobStatusResponse> | null>(null)

  useEffect(() => {
    if (jobId === null) {
      controllerRef.current = null
      return
    }
    const controller = new PollingController<ScoreSuggestionJobStatusResponse>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal,
      fetchFn: async () => {
        const response =
          await getScoreSuggestionStatusApiV1EvaluationsEvaluationIdProposalsProposalIdAiScoreSuggestionsJobIdGet(
            evaluationId,
            proposalId,
            jobId,
          )
        return unwrapDataOrThrow<ScoreSuggestionJobStatusResponse>(response)
      },
    })
    controllerRef.current = controller
    snapshotCacheRef.current = null
    controller.start()
    return () => {
      controller.dispose()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [evaluationId, proposalId, jobId])

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const current = controllerRef.current
      if (!current) return () => {}
      return current.subscribe(onStoreChange)
    },
    // See useReportJobStatus.ts: must match the construction effect's deps
    // (`[]` would subscribe once against a null controllerRef.current on the
    // `jobId === null` initial mount and never re-subscribe once a real
    // controller exists). Neither dep is read in the callback body, so
    // exhaustive-deps sees them as "unnecessary" - they're intentionally
    // there to drive resubscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [evaluationId, proposalId, jobId],
  )

  const getSnapshot = useCallback(() => {
    const raw = controllerRef.current?.getSnapshot() ?? null
    if (!snapshotsAreEqual(snapshotCacheRef.current, raw)) {
      snapshotCacheRef.current = raw
    }
    return snapshotCacheRef.current
  }, [])

  return useSyncExternalStore(subscribe, getSnapshot)
}
