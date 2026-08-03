import { useQueryClient } from '@tanstack/react-query'
import {
  getListPublishedQuestionsApiV1VendorPortalProposalsProposalIdQuestionsPublishedGetQueryKey,
  getListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGetQueryKey,
  useCreateQuestionApiV1VendorPortalProposalsProposalIdQuestionsPost,
  useWithdrawQuestionApiV1VendorPortalProposalsProposalIdQuestionsQuestionIdDelete,
  type QuestionCreateRequestScope,
} from '@/api/client'

/** Shared create/withdraw actions for a proposal's Q&A - ProposalQnaPanel
 * (general questions + peers' published board) and every per-requirement
 * RequirementQuestionThread instance each get their own hook instance, all
 * invalidating the same two list queries on success (own + published) so
 * every view stays in sync without prop-drilling a shared mutation - same
 * pattern as vendor-portal's useDocumentActions (Fase 16). */
export function useQuestionActions(proposalId: string) {
  const queryClient = useQueryClient()

  const invalidateLists = () => {
    queryClient.invalidateQueries({
      queryKey:
        getListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGetQueryKey(proposalId),
    })
    queryClient.invalidateQueries({
      queryKey:
        getListPublishedQuestionsApiV1VendorPortalProposalsProposalIdQuestionsPublishedGetQueryKey(
          proposalId,
        ),
    })
  }

  const createMutation = useCreateQuestionApiV1VendorPortalProposalsProposalIdQuestionsPost({
    mutation: { onSuccess: invalidateLists },
  })
  const withdrawMutation =
    useWithdrawQuestionApiV1VendorPortalProposalsProposalIdQuestionsQuestionIdDelete({
      mutation: { onSuccess: invalidateLists },
    })

  const create = (scope: QuestionCreateRequestScope, body: string, requirementId?: string) =>
    createMutation.mutate({
      proposalId,
      data: { scope, body, requirement_id: requirementId ?? null },
    })

  const withdraw = (questionId: string) => withdrawMutation.mutate({ proposalId, questionId })

  return {
    create,
    withdraw,
    isCreating: createMutation.isPending,
    isWithdrawing: withdrawMutation.isPending,
    createError: createMutation.error,
    withdrawError: withdrawMutation.error,
  }
}
