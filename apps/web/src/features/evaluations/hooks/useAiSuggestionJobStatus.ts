import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import {
  getRequirementSuggestionStatusApiV1EvaluationsEvaluationIdAiRequirementSuggestionsJobIdGet,
  type SuggestionJobStatusResponse,
} from '@/api/client'
import { unwrapDataOrThrow } from '@/lib/http'
import { PollingController, type PollingSnapshot } from '@/lib/pollingController'

// ADR 0012: 15s interval for job status (vs. 30s for collaborative screens).
const POLL_INTERVAL_MS = 15_000

function isTerminal(result: SuggestionJobStatusResponse): boolean {
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

/** First real consumer of `PollingController`/ADR 0012 - one controller
 * instance per job id, recreated only when the id changes. Returns `null`
 * while `jobId` is null (no job triggered yet), matching the "nothing to
 * poll" state the trigger button starts in.
 *
 * Fase 26 (Hardening): migrated to the same `useSyncExternalStore` +
 * memoized-snapshot shape as `useReportJobStatus.ts` (Fase 23) - the
 * original version built the controller directly in the render body and
 * read `controllerRef.current` synchronously as its return value, both
 * flagged unsafe by eslint-plugin-react-hooks 7's `react-hooks/refs`.
 * `useSyncExternalStore` is React's own sanctioned API for exactly this
 * "read a mutable external value during render" need. */
export function useAiSuggestionJobStatus(
  evaluationId: string,
  jobId: string | null,
): PollingSnapshot<SuggestionJobStatusResponse> | null {
  const controllerRef = useRef<PollingController<SuggestionJobStatusResponse> | null>(null)
  const snapshotCacheRef = useRef<PollingSnapshot<SuggestionJobStatusResponse> | null>(null)

  useEffect(() => {
    if (jobId === null) {
      controllerRef.current = null
      return
    }
    const controller = new PollingController<SuggestionJobStatusResponse>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal,
      fetchFn: async () => {
        const response =
          await getRequirementSuggestionStatusApiV1EvaluationsEvaluationIdAiRequirementSuggestionsJobIdGet(
            evaluationId,
            jobId,
          )
        return unwrapDataOrThrow<SuggestionJobStatusResponse>(response)
      },
    })
    controllerRef.current = controller
    snapshotCacheRef.current = null
    controller.start()
    return () => {
      controller.dispose()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [evaluationId, jobId])

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
    [evaluationId, jobId],
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
