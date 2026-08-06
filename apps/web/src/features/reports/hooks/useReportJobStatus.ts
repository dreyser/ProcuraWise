import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import {
  getReportApiV1EvaluationsEvaluationIdReportsReportIdGet,
  type ReportResponse,
} from '@/api/client'
import { unwrapDataOrThrow } from '@/lib/http'
import { PollingController, type PollingSnapshot } from '@/lib/pollingController'

// ADR 0012: 15s interval for job status, same cadence as the AI suggestion
// job this pattern is copied from (useAiSuggestionJobStatus.ts).
const POLL_INTERVAL_MS = 15_000

function isTerminal(result: ReportResponse): boolean {
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

/** Fase 23: one controller instance per report id, recreated only when the
 * id changes. Uses `useSyncExternalStore` (React's dedicated API for a
 * subscribe/getSnapshot external store like PollingController) rather than
 * useAiSuggestionJobStatus.ts's manual useState-tick pattern, because this
 * page also holds several concurrent `@tanstack/react-query` subscriptions
 * (readiness/list) - under React 19, a manually-ticked subscription's commit
 * can be dropped/reordered against those, whereas `useSyncExternalStore`
 * guarantees a consistent read. `PollingController.getSnapshot()` allocates
 * a fresh object every call, so `getSnapshot` here is memoized field-by-field
 * (snapshotsAreEqual) - required by `useSyncExternalStore`'s contract, since
 * returning a new reference on every render when nothing actually changed
 * causes it to conclude the store is tearing and re-render in a loop.
 * Returns `null` while `reportId` is null (no generation triggered yet). */
export function useReportJobStatus(
  evaluationId: string,
  reportId: string | null,
): PollingSnapshot<ReportResponse> | null {
  const controllerRef = useRef<{
    reportId: string
    controller: PollingController<ReportResponse>
  } | null>(null)
  const snapshotCacheRef = useRef<PollingSnapshot<ReportResponse> | null>(null)

  if (reportId === null && controllerRef.current) {
    controllerRef.current.controller.dispose()
    controllerRef.current = null
  }
  if (reportId !== null && controllerRef.current?.reportId !== reportId) {
    controllerRef.current?.controller.dispose()
    const controller = new PollingController<ReportResponse>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal,
      fetchFn: async () => {
        const response = await getReportApiV1EvaluationsEvaluationIdReportsReportIdGet(
          evaluationId,
          reportId,
        )
        return unwrapDataOrThrow<ReportResponse>(response)
      },
    })
    controllerRef.current = { reportId, controller }
    snapshotCacheRef.current = null
    controller.start()
  }

  useEffect(() => {
    return () => {
      controllerRef.current?.controller.dispose()
      controllerRef.current = null
    }
  }, [])

  const subscribe = useCallback((onStoreChange: () => void) => {
    const current = controllerRef.current
    if (!current) return () => {}
    return current.controller.subscribe(onStoreChange)
  }, [])

  const getSnapshot = useCallback(() => {
    const raw = controllerRef.current?.controller.getSnapshot() ?? null
    if (!snapshotsAreEqual(snapshotCacheRef.current, raw)) {
      snapshotCacheRef.current = raw
    }
    return snapshotCacheRef.current
  }, [])

  return useSyncExternalStore(subscribe, getSnapshot)
}
