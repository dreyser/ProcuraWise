import { useEffect, useRef, useState } from 'react'
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

/** First real consumer of `PollingController`/ADR 0012 - one controller
 * instance per job id, recreated only when the id changes (same ref-based
 * identity-check pattern as `useAnswerAutosave`). Returns `null` while
 * `jobId` is null (no job triggered yet), matching the "nothing to poll"
 * state the trigger button starts in. */
export function useAiSuggestionJobStatus(
  evaluationId: string,
  jobId: string | null,
): PollingSnapshot<SuggestionJobStatusResponse> | null {
  const controllerRef = useRef<{
    jobId: string
    controller: PollingController<SuggestionJobStatusResponse>
  } | null>(null)

  if (jobId === null && controllerRef.current) {
    controllerRef.current.controller.dispose()
    controllerRef.current = null
  }
  if (jobId !== null && controllerRef.current?.jobId !== jobId) {
    controllerRef.current?.controller.dispose()
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
    controllerRef.current = { jobId, controller }
    controller.start()
  }

  const [, setTick] = useState(0)
  useEffect(() => {
    const current = controllerRef.current
    if (!current) return
    return current.controller.subscribe(() => setTick((n) => n + 1))
  }, [jobId])

  useEffect(() => {
    return () => {
      controllerRef.current?.controller.dispose()
      controllerRef.current = null
    }
  }, [])

  return controllerRef.current?.controller.getSnapshot() ?? null
}
