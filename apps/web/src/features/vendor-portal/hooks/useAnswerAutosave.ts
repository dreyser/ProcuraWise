import { useEffect, useState } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey } from '@/api/client'
import { AnswerAutosaveController } from '@/lib/answerAutosaveController'

function createController(
  proposalId: string,
  version: number | undefined,
  queryClient: QueryClient,
): AnswerAutosaveController {
  return new AnswerAutosaveController(proposalId, version ?? 0, (response) => {
    queryClient.setQueryData(
      getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey(proposalId),
      response,
    )
  })
}

/** One controller instance per Proposal, recreated only when the proposal
 * id changes - re-renders are driven by subscribing to the controller
 * rather than by React state holding the queue itself (brief §20). Every
 * successful write is pushed back into the proposal's query cache so the
 * UI reflects the just-saved answer without a separate refetch.
 *
 * `version` may be `undefined` on first render (query still loading) - the
 * controller is seeded with a placeholder then, and the effect below syncs
 * it to the real value once the query resolves. Without this sync, a page
 * reload would recreate the controller before data arrives, "lock in" the
 * placeholder as its version forever, and every subsequent write (including
 * submit) would send a stale `expected_version` and 409 against itself. The
 * sync only applies while the controller is idle (no queued/in-flight
 * writes) so it never clobbers a write this same controller has in
 * flight.
 *
 * Fase 26 (Hardening): the caller (VendorProposalDetailPage.tsx) calls
 * imperative methods on the returned controller directly during render
 * (`controller.getStatus()`, `controller.getFieldError(...)`, ...), so this
 * hook cannot tolerate returning `null`/`undefined` while an effect catches
 * up the way the job-status hooks do - it must return a real controller
 * synchronously on every render, including the first. `useRef` mutated
 * during render was the previous approach but is now disallowed
 * (`react-hooks/refs`); `useState` + "adjust state during render" is
 * React's own sanctioned replacement for exactly this "reset internal
 * object when an id prop changes" need (https://react.dev/learn/you-might-
 * not-need-an-effect#adjusting-some-state-when-a-prop-changes) - calling
 * `setState` directly in the render body (not inside an effect) triggers
 * an immediate re-render before paint, which is different from the
 * "setState-in-effect" pattern that rule forbids. */
export function useAnswerAutosave(proposalId: string, version: number | undefined) {
  const queryClient = useQueryClient()
  const [state, setState] = useState(() => ({
    proposalId,
    controller: createController(proposalId, version, queryClient),
  }))

  if (state.proposalId !== proposalId) {
    setState({ proposalId, controller: createController(proposalId, version, queryClient) })
  }
  const controller = state.controller
  const [, setTick] = useState(0)

  useEffect(() => controller.subscribe(() => setTick((n) => n + 1)), [controller])

  useEffect(() => {
    if (
      version !== undefined &&
      controller.getStatus() === 'idle' &&
      controller.getPendingCount() === 0
    ) {
      controller.syncVersion(version)
    }
  }, [controller, version])

  return controller
}
