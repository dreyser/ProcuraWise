import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { getPurchaseApiV1BillingPurchasesPurchaseIdGet, type PurchaseResponse } from '@/api/client'
import { unwrapDataOrThrow } from '@/lib/http'
import { PollingController, type PollingSnapshot } from '@/lib/pollingController'

// ADR 0012: 3s interval - a payment confirmation, not a long-running job
// (contrast the 15s cadence useReportJobStatus.ts uses) - the wait is
// normally a few seconds at most (webhook delivery latency), and the
// frontend must never trust the success-page redirect's query params alone
// as proof of payment (plan S13.6/S13.8).
const POLL_INTERVAL_MS = 3_000

function isTerminal(result: PurchaseResponse): boolean {
  return result.status === 'paid' || result.status === 'expired'
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

/** Fase 25 (billing/admin, ADR 0025) - same useSyncExternalStore + memoized-
 * snapshot pattern as features/reports/hooks/useReportJobStatus.ts (Fase 23),
 * copied deliberately rather than shared, since the two hooks poll different
 * resources with different terminal conditions/intervals. The webhook is the
 * only source of truth for "paid" - this hook is what lets
 * CheckoutSuccessPage reflect that instead of trusting the redirect's own
 * query params.
 *
 * Unlike useReportJobStatus.ts, the controller is built inside useEffect
 * rather than during render: this page is reached right after a hard
 * browser navigation (Checkout redirect) that can force a real re-mount in
 * quick succession, and StrictMode's dev-only simulated unmount+remount
 * only re-runs effects, not the render body - a controller constructed
 * during render would get disposed by the simulated unmount's cleanup and
 * never rebuilt, leaving controllerRef.current permanently null. Building
 * it in the effect means the simulated remount's effect re-run reconstructs
 * it correctly, same as any other effect-owned resource. */
export function usePurchaseStatus(purchaseId: string): PollingSnapshot<PurchaseResponse> | null {
  const controllerRef = useRef<PollingController<PurchaseResponse> | null>(null)
  const snapshotCacheRef = useRef<PollingSnapshot<PurchaseResponse> | null>(null)

  useEffect(() => {
    const controller = new PollingController<PurchaseResponse>({
      intervalMs: POLL_INTERVAL_MS,
      isTerminal,
      fetchFn: async () => {
        const response = await getPurchaseApiV1BillingPurchasesPurchaseIdGet(purchaseId)
        return unwrapDataOrThrow<PurchaseResponse>(response)
      },
    })
    controllerRef.current = controller
    snapshotCacheRef.current = null
    controller.start()
    return () => {
      controller.dispose()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [purchaseId])

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const current = controllerRef.current
      if (!current) return () => {}
      return current.subscribe(onStoreChange)
    },
    // See useReportJobStatus.ts (Fase 26): must match the construction
    // effect's deps, or a controller rebuild (purchaseId change without a
    // full remount) would leave this hook subscribed to nothing. Not read in
    // the callback body, so exhaustive-deps sees it as "unnecessary" - it's
    // intentionally there to drive resubscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [purchaseId],
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
