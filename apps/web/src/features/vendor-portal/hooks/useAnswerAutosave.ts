import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey } from '@/api/client'
import { AnswerAutosaveController } from '@/lib/answerAutosaveController'

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
 * flight. */
export function useAnswerAutosave(proposalId: string, version: number | undefined) {
  const queryClient = useQueryClient()
  const controllerRef = useRef<AnswerAutosaveController | null>(null)
  if (!controllerRef.current || controllerRef.current.proposalId !== proposalId) {
    controllerRef.current = new AnswerAutosaveController(proposalId, version ?? 0, (response) => {
      queryClient.setQueryData(
        getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey(proposalId),
        response,
      )
    })
  }
  const controller = controllerRef.current
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
