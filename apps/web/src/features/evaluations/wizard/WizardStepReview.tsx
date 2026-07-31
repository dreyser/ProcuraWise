import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useRequestApprovalApiV1EvaluationsEvaluationIdRequestApprovalPost,
  useSetApproverApiV1EvaluationsEvaluationIdApproverPost,
  useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost,
  useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch,
  useWithdrawApprovalRequestApiV1EvaluationsEvaluationIdRequestApprovalDelete,
  useListOrgMembersApiV1OrgMembersGet,
  type EvaluationDetailResponse,
  type OrgMembersListResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge } from '@/components/StatusBadge'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { translateApprovalStatus } from '@/lib/enumLabels'
import {
  requestApprovalPreconditionReasons,
  startCollectionPreconditionReasons,
} from '@/features/evaluations/lib/evaluationReadiness'

interface WizardStepReviewProps {
  evaluation: EvaluationDetailResponse
  onBack: () => void
  onStarted: () => void
}

/** Step 4. Reuses the exact start-collection confirmation copy already
 * established in `VendorsPage` - the wizard's last step is what actually
 * closes "creation" by moving the evaluation into `collecting_responses`.
 *
 * Fase 12: approval_status is orthogonal to the wizard's own 4 structural
 * steps (deriveWizardStep is untouched - approval never changes
 * EvaluationStatus, plan §9.A), so this step becomes approval_status-aware
 * rather than a wizard step 5. "Iniciar recepción de propuestas" IS publish
 * (plan §9.B) - same button, same mutation, now additionally gated on
 * approval_status === "approved". */
export function WizardStepReview({ evaluation, onBack, onStarted }: WizardStepReviewProps) {
  const queryClient = useQueryClient()
  const [confirmStart, setConfirmStart] = useState(false)
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const [selectedApproverId, setSelectedApproverId] = useState('')
  const [deadline, setDeadline] = useState('')

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet()
  const approvers = (unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []).filter(
    (member) => member.role === 'approver',
  )

  const setEvaluationCache = (response: unknown) => {
    queryClient.setQueryData(
      getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
      response,
    )
  }

  const setApprover = useSetApproverApiV1EvaluationsEvaluationIdApproverPost({
    mutation: { onSuccess: setEvaluationCache },
  })
  const updateDeadline = useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch({
    mutation: { onSuccess: setEvaluationCache },
  })
  const requestApproval = useRequestApprovalApiV1EvaluationsEvaluationIdRequestApprovalPost({
    mutation: { onSuccess: setEvaluationCache },
  })
  const withdrawRequest =
    useWithdrawApprovalRequestApiV1EvaluationsEvaluationIdRequestApprovalDelete({
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
          })
          setConfirmWithdraw(false)
        },
      },
    })
  const startCollection = useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost({
    mutation: {
      onSuccess: (response) => {
        setEvaluationCache(response)
        setConfirmStart(false)
        onStarted()
      },
    },
  })

  const reasons = startCollectionPreconditionReasons(evaluation)
  const canStart = reasons.length === 0
  const functionalCount = evaluation.requirements.filter((r) => r.dimension === 'functional').length
  const technicalCount = evaluation.requirements.filter((r) => r.dimension === 'technical').length

  // Preview against the locally-selected approver/deadline, not just the
  // last-persisted server values - otherwise the button stays disabled
  // until a request already succeeded, which is exactly the request it's
  // meant to trigger in the first place.
  const effectiveApproverId = selectedApproverId || evaluation.approver_membership_id
  const effectiveDeadline = deadline
    ? new Date(`${deadline}T00:00:00Z`).toISOString()
    : evaluation.response_deadline
  const requestReasons = requestApprovalPreconditionReasons({
    ...evaluation,
    approver_membership_id: effectiveApproverId,
    response_deadline: effectiveDeadline,
  })
  const canRequestApproval = requestReasons.length === 0
  const requestPending =
    setApprover.isPending || updateDeadline.isPending || requestApproval.isPending
  const requestError = setApprover.isError
    ? setApprover.error
    : updateDeadline.isError
      ? updateDeadline.error
      : requestApproval.isError
        ? requestApproval.error
        : null

  const handleRequestApproval = async () => {
    try {
      const approverToSet = selectedApproverId || evaluation.approver_membership_id
      if (approverToSet && approverToSet !== evaluation.approver_membership_id) {
        await setApprover.mutateAsync({
          evaluationId: evaluation.id,
          data: { approver_membership_id: approverToSet },
        })
      }
      const deadlineIso = deadline ? new Date(`${deadline}T00:00:00Z`).toISOString() : null
      if (deadlineIso && deadlineIso !== evaluation.response_deadline) {
        await updateDeadline.mutateAsync({
          evaluationId: evaluation.id,
          data: { response_deadline: deadlineIso },
        })
      }
      await requestApproval.mutateAsync({ evaluationId: evaluation.id })
    } catch {
      // Surfaced via the individual mutations' own isError/error state below.
    }
  }

  return (
    <div>
      <dl className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-muted-foreground">Requerimientos funcionales</dt>
          <dd className="text-foreground">{functionalCount}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Requerimientos técnicos</dt>
          <dd className="text-foreground">{technicalCount}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Proveedores vinculados</dt>
          <dd className="text-foreground">{evaluation.linked_vendor_count} / 6</dd>
        </div>
      </dl>

      <section className="mt-8 max-w-md">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">Aprobación</h2>
          <StatusBadge label={translateApprovalStatus(evaluation.approval_status)} />
        </div>

        {(evaluation.approval_status === 'not_requested' ||
          evaluation.approval_status === 'rejected') && (
          <div className="mt-3 flex flex-col gap-3">
            {evaluation.approval_status === 'rejected' && evaluation.approval_comment && (
              <ErrorBanner
                variant="info"
                message={`Comentario del aprobador: ${evaluation.approval_comment}`}
              />
            )}
            <div>
              <Label htmlFor="wizard-approver-select">Aprobador</Label>
              <Select
                value={selectedApproverId || evaluation.approver_membership_id || undefined}
                onValueChange={setSelectedApproverId}
              >
                <SelectTrigger id="wizard-approver-select" className="w-full">
                  <SelectValue placeholder="Selecciona un aprobador" />
                </SelectTrigger>
                <SelectContent>
                  {approvers.length === 0 ? (
                    <SelectItem value="" disabled>
                      Sin aprobadores en tu organización
                    </SelectItem>
                  ) : (
                    approvers.map((member) => (
                      <SelectItem key={member.membership_id} value={member.membership_id}>
                        {member.display_name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="wizard-response-deadline">Fecha límite de respuesta</Label>
              <Input
                id="wizard-response-deadline"
                type="date"
                defaultValue={
                  evaluation.response_deadline ? evaluation.response_deadline.slice(0, 10) : ''
                }
                onChange={(event) => setDeadline(event.target.value)}
              />
            </div>
            {requestError && <ErrorBanner message={normalizeApiError(requestError).message} />}
            <Button
              type="button"
              disabled={!canRequestApproval || requestPending}
              onClick={handleRequestApproval}
            >
              {requestPending ? 'Solicitando…' : 'Solicitar aprobación'}
            </Button>
            <DisabledActionHint reasons={canRequestApproval ? [] : requestReasons} />
          </div>
        )}

        {evaluation.approval_status === 'pending' && (
          <div className="mt-3">
            <p className="text-sm text-muted-foreground">
              Esperando la decisión del aprobador asignado.
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-2"
              onClick={() => setConfirmWithdraw(true)}
            >
              Retirar solicitud
            </Button>
          </div>
        )}

        {evaluation.approval_status === 'approved' && (
          <p className="mt-3 text-sm text-muted-foreground">
            Evaluación aprobada. Ya puedes publicarla para comenzar a recibir propuestas.
          </p>
        )}
      </section>

      <div className="mt-8 flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onBack}>
          Atrás
        </Button>
        <Button type="button" disabled={!canStart} onClick={() => setConfirmStart(true)}>
          Iniciar recepción de propuestas
        </Button>
      </div>
      <DisabledActionHint reasons={canStart ? [] : reasons} />
      {startCollection.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(startCollection.error).message} />
        </div>
      )}

      <ConfirmDialog
        open={confirmStart}
        onOpenChange={setConfirmStart}
        title="Iniciar recepción de propuestas"
        description="Los requerimientos y proveedores quedarán en modo de solo lectura. Los proveedores vinculados podrán empezar a responder."
        confirmLabel="Iniciar recepción"
        isPending={startCollection.isPending}
        onConfirm={() => startCollection.mutate({ evaluationId: evaluation.id })}
      />

      <ConfirmDialog
        open={confirmWithdraw}
        onOpenChange={setConfirmWithdraw}
        title="Retirar solicitud de aprobación"
        description="El aprobador ya no podrá decidir sobre esta solicitud hasta que la vuelvas a enviar."
        confirmLabel="Retirar solicitud"
        variant="destructive"
        isPending={withdrawRequest.isPending}
        onConfirm={() => withdrawRequest.mutate({ evaluationId: evaluation.id })}
      />
    </div>
  )
}
