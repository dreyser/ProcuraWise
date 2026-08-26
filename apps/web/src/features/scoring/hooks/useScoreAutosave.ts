import { useEffect, useState } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey } from '@/api/client'
import { ScoreAutosaveController } from '@/lib/scoreAutosaveController'

function createController(
  evaluationId: string,
  proposalId: string,
  queryClient: QueryClient,
): ScoreAutosaveController {
  return new ScoreAutosaveController(evaluationId, proposalId, () => {
    // Unlike AnswerAutosaveController (whole-proposal detail response
    // replaces the cache wholesale), a saved Score is one row nested three
    // levels deep inside ResultsResponse.proposals[].scores[] - refetching
    // is simpler and less error-prone than hand-patching that structure,
    // and matches what the pre-autosave manual "Guardar calificación"
    // button already did after every save.
    void queryClient.invalidateQueries({
      queryKey: getGetResultsApiV1EvaluationsEvaluationIdResultsGetQueryKey(evaluationId),
    })
  })
}

/** One controller instance per (evaluation, proposal) pair - mirrors
 * useAnswerAutosave's "recreate only when the id changes, re-render by
 * subscribing" shape (brief §20). Unlike the vendor hook, there is no
 * single version to sync from an effect: callers seed each field's known
 * version individually via `controller.seedVersionIfIdle(...)` as results
 * data loads (see ScoringPage.tsx), since every requirement's Score has
 * its own independent version. */
export function useScoreAutosave(evaluationId: string, proposalId: string) {
  const queryClient = useQueryClient()
  const key = `${evaluationId}:${proposalId}`
  const [state, setState] = useState(() => ({
    key,
    controller: createController(evaluationId, proposalId, queryClient),
  }))

  if (state.key !== key) {
    setState({ key, controller: createController(evaluationId, proposalId, queryClient) })
  }
  const controller = state.controller
  const [, setTick] = useState(0)

  useEffect(() => controller.subscribe(() => setTick((n) => n + 1)), [controller])

  return controller
}
