import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useApproveEvaluationApiV1EvaluationsEvaluationIdApprovePost,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetSnapshotApiV1EvaluationsEvaluationIdSnapshotGet,
  useListOrgMembersApiV1OrgMembersGet,
  useRejectEvaluationApiV1EvaluationsEvaluationIdRejectPost,
  useRequestApprovalApiV1EvaluationsEvaluationIdRequestApprovalPost,
  useSetApproverApiV1EvaluationsEvaluationIdApproverPost,
  useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch,
  useWithdrawApprovalRequestApiV1EvaluationsEvaluationIdRequestApprovalDelete,
  type EvaluationDetailResponse,
  type EvaluationSnapshotResponse,
  type OrgMembersListResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { translateApprovalStatus, translateEvaluationStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import { requestApprovalPreconditionReasons } from '@/features/evaluations/lib/evaluationReadiness'

/** "Aprobación" tab (Fase 12): reachable by every BUYER_READ_ROLES actor for
 * visibility, but the approve/reject controls only render for the
 * evaluation's own assigned approver (backend re-enforces this - route
 * guards here are UX only, brief §17). Lives on its own route rather than
 * inside the wizard because the wizard is owner-only
 * (EvaluationWizard.tsx redirects any non-owner away) and the approver is,
 * by design, never the owner (self-approval is blocked server-side). */
export function EvaluationApprovalPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)
  const isAssignedApprover =
    actor?.role === 'approver' && actor.membership_id === evaluation?.approver_membership_id

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet({ query: { enabled: isOwner } })
  const orgMembers = unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []
  const approvers = orgMembers.filter((member) => member.role === 'approver')
  const memberLabel = (membershipId: string | null): string | null => {
    if (!membershipId) return null
    return orgMembers.find((member) => member.membership_id === membershipId)?.display_name ?? null
  }

  const snapshotQuery = useGetSnapshotApiV1EvaluationsEvaluationIdSnapshotGet(evaluationId!, {
    query: { enabled: Boolean(evaluation?.approval_snapshot_id) },
  })

  const [selectedApproverId, setSelectedApproverId] = useState('')
  const [deadline, setDeadline] = useState('')
  const [comment, setComment] = useState('')
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)

  const invalidateEvaluation = () =>
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
    })

  const setApprover = useSetApproverApiV1EvaluationsEvaluationIdApproverPost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const updateDeadline = useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const requestApproval = useRequestApprovalApiV1EvaluationsEvaluationIdRequestApprovalPost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const withdrawRequest =
    useWithdrawApprovalRequestApiV1EvaluationsEvaluationIdRequestApprovalDelete({
      mutation: {
        onSuccess: () => {
          invalidateEvaluation()
          setConfirmWithdraw(false)
        },
      },
    })
  const approveEvaluation = useApproveEvaluationApiV1EvaluationsEvaluationIdApprovePost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const rejectEvaluation = useRejectEvaluationApiV1EvaluationsEvaluationIdRejectPost({
    mutation: {
      onSuccess: () => {
        invalidateEvaluation()
        setConfirmReject(false)
        setComment('')
      },
    },
  })

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando aprobación…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  const canConfigure =
    isOwner &&
    evaluation.status === 'draft' &&
    (evaluation.approval_status === 'not_requested' || evaluation.approval_status === 'rejected')
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
  const canRequestApproval = canConfigure && requestReasons.length === 0
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
      // Surfaced via the individual mutations' own isError/error state above.
    }
  }

  const requestedByLabel = memberLabel(evaluation.approval_requested_by_membership_id)
  const decidedByLabel = memberLabel(evaluation.approval_decided_by_membership_id)

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      <section className="mt-6">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">Estado de aprobación</h2>
          <StatusBadge label={translateApprovalStatus(evaluation.approval_status)} />
        </div>

        <dl className="mt-3 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Fecha límite de respuesta</dt>
            <dd className="text-foreground">
              {evaluation.response_deadline
                ? new Date(evaluation.response_deadline).toLocaleDateString()
                : 'Sin definir'}
            </dd>
          </div>
          {evaluation.approval_requested_at && (
            <div>
              <dt className="text-muted-foreground">Solicitada</dt>
              <dd className="text-foreground">
                {new Date(evaluation.approval_requested_at).toLocaleString()}
                {requestedByLabel ? ` · ${requestedByLabel}` : ''}
              </dd>
            </div>
          )}
          {evaluation.approval_decided_at && (
            <div>
              <dt className="text-muted-foreground">
                {evaluation.approval_status === 'rejected' ? 'Rechazada' : 'Decidida'}
              </dt>
              <dd className="text-foreground">
                {new Date(evaluation.approval_decided_at).toLocaleString()}
                {decidedByLabel ? ` · ${decidedByLabel}` : ''}
              </dd>
            </div>
          )}
        </dl>
        {evaluation.approval_comment && (
          <p className="mt-3 text-sm text-muted-foreground">
            Comentario: {evaluation.approval_comment}
          </p>
        )}
      </section>

      {canConfigure && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Solicitar aprobación</h2>
          <div className="mt-3 flex flex-col gap-3">
            <div>
              <Label htmlFor="approval-approver-select">Aprobador</Label>
              <Select
                value={selectedApproverId || evaluation.approver_membership_id || undefined}
                onValueChange={setSelectedApproverId}
              >
                <SelectTrigger id="approval-approver-select" className="w-full">
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
              <Label htmlFor="approval-response-deadline">Fecha límite de respuesta</Label>
              <Input
                id="approval-response-deadline"
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
              className="self-start"
              disabled={!canRequestApproval || requestPending}
              onClick={handleRequestApproval}
            >
              {requestPending ? 'Solicitando…' : 'Solicitar aprobación'}
            </Button>
            <DisabledActionHint reasons={canRequestApproval ? [] : requestReasons} />
          </div>
        </section>
      )}

      {isOwner && evaluation.approval_status === 'pending' && (
        <section className="mt-6">
          <Button type="button" variant="outline" onClick={() => setConfirmWithdraw(true)}>
            Retirar solicitud
          </Button>
        </section>
      )}

      {isAssignedApprover && evaluation.approval_status === 'pending' && (
        <section className="mt-6 max-w-lg">
          <h2 className="text-sm font-semibold text-foreground">Tu decisión</h2>
          <div className="mt-3 flex flex-col gap-3">
            <div>
              <Label htmlFor="approval-comment">Comentario (obligatorio para rechazar)</Label>
              <Textarea
                id="approval-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
            </div>
            {(approveEvaluation.isError || rejectEvaluation.isError) && (
              <ErrorBanner
                message={
                  normalizeApiError(approveEvaluation.error ?? rejectEvaluation.error).message
                }
              />
            )}
            <div className="flex gap-2">
              <Button
                type="button"
                disabled={approveEvaluation.isPending}
                onClick={() =>
                  approveEvaluation.mutate({
                    evaluationId: evaluation.id,
                    data: { comment: comment || null },
                  })
                }
              >
                {approveEvaluation.isPending ? 'Aprobando…' : 'Aprobar'}
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={!comment.trim()}
                onClick={() => setConfirmReject(true)}
              >
                Rechazar
              </Button>
            </div>
            <DisabledActionHint
              reasons={comment.trim() ? [] : ['Debes escribir un comentario para rechazar.']}
            />
          </div>
        </section>
      )}

      {evaluation.approval_snapshot_id && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Snapshot de publicación</h2>
          {snapshotQuery.isLoading && <LoadingState label="Cargando snapshot…" />}
          {snapshotQuery.error && (
            <ErrorBanner message={normalizeApiError(snapshotQuery.error).message} />
          )}
          {snapshotQuery.data && (
            <p className="mt-2 text-sm text-muted-foreground">
              Publicada el{' '}
              {new Date(
                unwrapData<EvaluationSnapshotResponse>(snapshotQuery.data)?.published_at ?? '',
              ).toLocaleString()}{' '}
              — los términos aprobados quedaron congelados de forma permanente.
            </p>
          )}
        </section>
      )}

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

      <ConfirmDialog
        open={confirmReject}
        onOpenChange={setConfirmReject}
        title="Rechazar evaluación"
        description="El responsable de evaluación verá tu comentario y podrá editar y volver a solicitar aprobación."
        confirmLabel="Rechazar"
        variant="destructive"
        isPending={rejectEvaluation.isPending}
        onConfirm={() =>
          rejectEvaluation.mutate({ evaluationId: evaluation.id, data: { comment } })
        }
      />
    </div>
  )
}
