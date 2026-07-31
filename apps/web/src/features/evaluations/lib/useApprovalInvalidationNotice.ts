import { useEffect, useRef, useState } from 'react'
import type { EvaluationDetailResponse } from '@/api/client'

type ApprovalStatus = EvaluationDetailResponse['approval_status']

const INVALIDATED_FROM: readonly ApprovalStatus[] = ['pending', 'approved']

export const APPROVAL_INVALIDATED_MESSAGE =
  'La solicitud de aprobación fue retirada porque se modificó la evaluación — deberás solicitarla nuevamente.'

/** Watches an evaluation's approval_status across renders and surfaces an
 * explicit, dismissible notice the moment it reverts to "not_requested" as
 * a side effect of a draft-gated edit (backend soft-invalidation, plan §14/
 * §32 Blocker 3) - never just a silently-updated StatusBadge discovered
 * later. Ref-based rather than reading a mutation's own response body,
 * because add/update/delete-requirement return the Requirement, not the
 * Evaluation - this only needs the evaluation query's value to change
 * across renders (however that refetch was triggered) to notice. */
export function useApprovalInvalidationNotice(approvalStatus: ApprovalStatus | undefined): {
  visible: boolean
  dismiss: () => void
} {
  const previousRef = useRef(approvalStatus)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const previous = previousRef.current
    if (
      previous !== undefined &&
      INVALIDATED_FROM.includes(previous) &&
      approvalStatus === 'not_requested'
    ) {
      setVisible(true)
    }
    previousRef.current = approvalStatus
  }, [approvalStatus])

  return { visible, dismiss: () => setVisible(false) }
}
