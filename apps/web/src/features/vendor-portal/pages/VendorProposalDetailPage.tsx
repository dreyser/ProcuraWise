import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey,
  getListProposalsApiV1VendorPortalProposalsGetQueryKey,
  useGetProposalApiV1VendorPortalProposalsProposalIdGet,
  useSubmitProposalApiV1VendorPortalProposalsProposalIdSubmitPost,
  type VendorProposalDetailResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { StatusBadge } from '@/components/StatusBadge'
import { PriorityBadge } from '@/components/PriorityBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { translateProposalStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { useAnswerAutosave } from '@/features/vendor-portal/hooks/useAnswerAutosave'
import { AnswerField } from '@/features/vendor-portal/components/AnswerField'
import { ProposalDocumentsPanel } from '@/features/vendor-portal/components/ProposalDocumentsPanel'
import { RequirementEvidenceUpload } from '@/features/vendor-portal/components/RequirementEvidenceUpload'

export function VendorProposalDetailPage() {
  const { proposalId } = useParams<{ proposalId: string }>()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useGetProposalApiV1VendorPortalProposalsProposalIdGet(
    proposalId!,
  )
  const proposal = unwrapData<VendorProposalDetailResponse>(data)

  const controller = useAnswerAutosave(proposalId!, proposal?.version)
  const [confirmSubmit, setConfirmSubmit] = useState(false)

  const submitProposal = useSubmitProposalApiV1VendorPortalProposalsProposalIdSubmitPost({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(
          getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey(proposalId),
          response,
        )
        queryClient.invalidateQueries({
          queryKey: getListProposalsApiV1VendorPortalProposalsGetQueryKey(),
        })
        setConfirmSubmit(false)
      },
    },
  })

  if (isLoading) return <LoadingState label="Cargando propuesta…" />
  if (error instanceof ApiError && error.status === 404) {
    return <ErrorBanner message="Esta propuesta no está disponible." />
  }
  if (error) return <ErrorBanner message={normalizeApiError(error).message} />
  if (!proposal) return null

  const isSubmitted = proposal.status === 'submitted'
  const requirements = [...proposal.requirements].sort((a, b) => a.display_order - b.display_order)
  const answerByRequirementId = new Map(proposal.answers.map((a) => [a.requirement_id, a]))

  const isAnswered = (requirementId: string) => {
    const answer = answerByRequirementId.get(requirementId)
    return answer !== undefined && answer.value !== null && answer.value !== undefined
  }

  const answeredCount = requirements.filter((r) => isAnswered(r.id)).length
  const pendingRequired = requirements.filter((r) => r.required && !isAnswered(r.id))

  const handleReloadAfterConflict = async () => {
    const queryKey = getGetProposalApiV1VendorPortalProposalsProposalIdGetQueryKey(proposalId)
    await queryClient.refetchQueries({ queryKey })
    const fresh = unwrapData<VendorProposalDetailResponse>(queryClient.getQueryData(queryKey))
    if (fresh) controller.syncVersion(fresh.version)
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{proposal.evaluation_name}</h1>
        <StatusBadge label={translateProposalStatus(proposal.status)} />
      </div>

      {isSubmitted ? (
        <p className="mt-2 text-sm text-muted-foreground">
          Esta propuesta ya fue enviada y no puede editarse.
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted-foreground" role="status">
          <span>
            Respondidos: {answeredCount} / {requirements.length}
          </span>
          <span>Obligatorios pendientes: {pendingRequired.length}</span>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-6">
        {requirements.map((requirement) => {
          const answer = answerByRequirementId.get(requirement.id)
          const fieldError = controller.getFieldError(requirement.id)
          return (
            <div key={requirement.id} className="rounded-md border border-border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold text-foreground">{requirement.title}</h2>
                <PriorityBadge priority={requirement.priority} />
                {requirement.required && <StatusBadge label="Obligatorio" />}
                {!isSubmitted && controller.isFieldPending(requirement.id) && (
                  <span className="text-xs text-muted-foreground">Guardando…</span>
                )}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{requirement.description}</p>
              {requirement.buyer_guidance && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Guía del comprador: {requirement.buyer_guidance}
                </p>
              )}

              <div className="mt-3">
                <AnswerField
                  requirement={requirement}
                  value={answer?.value ?? null}
                  vendorComment={answer?.vendor_comment ?? null}
                  disabled={isSubmitted || controller.getStatus() === 'conflict'}
                  readOnly={isSubmitted}
                  error={fieldError?.message}
                  onCommit={(value, vendorComment) =>
                    controller.queueAnswer(requirement.id, value, vendorComment)
                  }
                />
              </div>

              <RequirementEvidenceUpload
                proposalId={proposalId!}
                requirementId={requirement.id}
                disabled={isSubmitted}
              />
            </div>
          )
        })}
      </div>

      <div className="mt-6">
        <ProposalDocumentsPanel proposalId={proposalId!} disabled={isSubmitted} />
      </div>

      {!isSubmitted && (
        <div className="mt-6">
          {submitProposal.isError && (
            <div className="mb-2">
              <ErrorBanner message={normalizeApiError(submitProposal.error).message} />
            </div>
          )}
          <Button
            type="button"
            disabled={controller.getPendingCount() > 0 || pendingRequired.length > 0}
            onClick={() => setConfirmSubmit(true)}
          >
            Enviar propuesta
          </Button>
          {controller.getPendingCount() > 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              Espera a que se guarden los cambios pendientes antes de enviar.
            </p>
          )}
          {controller.getPendingCount() === 0 && pendingRequired.length > 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              Responde los requerimientos obligatorios antes de enviar.
            </p>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmSubmit}
        onOpenChange={setConfirmSubmit}
        title="Enviar propuesta"
        description="Una vez enviada, la propuesta queda congelada y ya no podrás editar tus respuestas."
        confirmLabel="Enviar propuesta"
        isPending={submitProposal.isPending}
        onConfirm={() =>
          submitProposal.mutate({
            proposalId: proposal.id,
            data: { expected_version: controller.getCurrentVersion() },
          })
        }
      />

      <ConfirmDialog
        open={controller.getStatus() === 'conflict'}
        onOpenChange={() => {}}
        title="Los datos cambiaron"
        description="Esta propuesta fue modificada desde que la cargaste. Recarga para continuar; los cambios sin guardar se perderán."
        confirmLabel="Recargar"
        onConfirm={handleReloadAfterConflict}
      />
    </div>
  )
}
