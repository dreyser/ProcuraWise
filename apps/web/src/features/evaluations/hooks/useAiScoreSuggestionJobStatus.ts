import { useEffect, useRef, useState } from 'react'
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

/** Fase 18 (ADR 0022): second real consumer of `PollingController` for a job
 * status screen. Unlike useAiSuggestionJobStatus.ts (Fase 13), which creates
 * and starts the controller directly in the render body and subscribes in a
 * separate effect afterward, this subscribes *before* starting, both inside
 * the same effect - with a fast-resolving fetch (real network latency is
 * never that fast, but a mocked one in tests can be), `controller.start()`
 * can resolve and call `notify()` before a render-body-created controller's
 * own subscribe effect has had a chance to run, silently dropping the one
 * and only update that would have flipped the UI out of "generating…". Kept
 * local to this hook rather than changing the Fase 13 one, which is already
 * shipped and tested against its current contract. */
export function useAiScoreSuggestionJobStatus(
  evaluationId: string,
  proposalId: string,
  jobId: string | null,
): PollingSnapshot<ScoreSuggestionJobStatusResponse> | null {
  const [snapshot, setSnapshot] =
    useState<PollingSnapshot<ScoreSuggestionJobStatusResponse> | null>(null)
  const controllerRef = useRef<PollingController<ScoreSuggestionJobStatusResponse> | null>(null)

  useEffect(() => {
    if (jobId === null) {
      setSnapshot(null)
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
    const unsubscribe = controller.subscribe(() => setSnapshot(controller.getSnapshot()))
    setSnapshot(controller.getSnapshot())
    controller.start()

    return () => {
      unsubscribe()
      controller.dispose()
      controllerRef.current = null
    }
  }, [evaluationId, proposalId, jobId])

  return snapshot
}
