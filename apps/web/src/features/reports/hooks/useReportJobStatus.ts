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
 * Returns `null` while `reportId` is null (no generation triggered yet).
 *
 * Fase 26 (Hardening): the controller is built inside `useEffect`, not
 * during render - the previous version constructed/disposed it directly in
 * the render body (comparing `controllerRef.current?.reportId` against the
 * latest `reportId` on every call), which `eslint-plugin-react-hooks`
 * 7.x's new `react-hooks/refs` rule correctly flags as unsafe (accessing/
 * mutating a ref's `.current` during render can be silently dropped or
 * duplicated by React, e.g. under Strict Mode's simulated remount - see
 * `usePurchaseStatus.ts`, Fase 25, which hit the exact same class of bug for
 * a different reason and already established this pattern). Keying the
 * effect on `[evaluationId, reportId]` reproduces the original render-time
 * logic correctly: React runs the previous effect's cleanup (disposing the
 * old controller) before the new one whenever either id changes, including
 * the `reportId: string -> null` transition. */
export function useReportJobStatus(
  evaluationId: string,
  reportId: string | null,
): PollingSnapshot<ReportResponse> | null {
  const controllerRef = useRef<PollingController<ReportResponse> | null>(null)
  const snapshotCacheRef = useRef<PollingSnapshot<ReportResponse> | null>(null)

  useEffect(() => {
    if (reportId === null) {
      controllerRef.current = null
      return
    }
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
    controllerRef.current = controller
    snapshotCacheRef.current = null
    controller.start()
    return () => {
      controller.dispose()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [evaluationId, reportId])

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const current = controllerRef.current
      if (!current) return () => {}
      return current.subscribe(onStoreChange)
    },
    // `reportId`/`evaluationId` (not `[]`) so this identity changes exactly
    // when the effect above (re)builds the controller. useSyncExternalStore
    // only re-subscribes when `subscribe` itself changes identity - with a
    // `[]`-deps version, a `reportId: null -> string` transition (starting
    // this hook with no controller yet, the common case) subscribes once at
    // mount against a null controllerRef.current, permanently as a no-op,
    // and never re-subscribes once the real controller exists later, so
    // notify() calls are silently dropped and the UI never updates. Neither
    // dep is read in the callback body, so exhaustive-deps sees them as
    // "unnecessary" - they're intentionally there to drive resubscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [evaluationId, reportId],
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
