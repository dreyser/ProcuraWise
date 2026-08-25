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
  useRequestReviewApiV1EvaluationsEvaluationIdRequestReviewPost,
  useReviewApproveApiV1EvaluationsEvaluationIdReviewApprovePost,
  useReviewRejectApiV1EvaluationsEvaluationIdReviewRejectPost,
  useSetApproverApiV1EvaluationsEvaluationIdApproverPost,
  useSetReviewerApiV1EvaluationsEvaluationIdReviewerPost,
  useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch,
  useWithdrawApprovalRequestApiV1EvaluationsEvaluationIdRequestApprovalDelete,
  useWithdrawReviewRequestApiV1EvaluationsEvaluationIdRequestReviewDelete,
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
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  translateApprovalStatus,
  translateEvaluationStatus,
  translateReviewStatus,
} from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import {
  requestApprovalPreconditionReasons,
  requestReviewPreconditionReasons,
} from '@/features/evaluations/lib/evaluationReadiness'

/** ADR 0026 (R2) - shared by both the reviewer's and the approver's own
 * reject flow: per-requirement comments, only sent when at least one is
 * non-empty, and only meaningful when the decision is flagged as "solicitar
 * cambios" rather than a generic rejection (blocking question resolved
 * 2026-08-24 - both persist the same rejected status, distinguished only in
 * the audit trail). */
function RequirementNotesEditor({
  requirements,
  notes,
  onChange,
}: {
  requirements: EvaluationDetailResponse['requirements']
  notes: Record<string, string>
  onChange: (requirementId: string, value: string) => void
}) {
  if (requirements.length === 0) return null
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">
        Comentario por requerimiento (opcional, se preserva individualmente):
      </p>
      {requirements.map((requirement) => (
        <div key={requirement.id}>
          <Label htmlFor={`requirement-note-${requirement.id}`} className="text-xs">
            {requirement.title}
          </Label>
          <Input
            id={`requirement-note-${requirement.id}`}
            value={notes[requirement.id] ?? ''}
            onChange={(event) => onChange(requirement.id, event.target.value)}
          />
        </div>
      ))}
    </div>
  )
}

function buildRequirementNotes(
  notes: Record<string, string>,
): { requirement_id: string; comment: string }[] | null {
  const entries = Object.entries(notes)
    .filter(([, value]) => value.trim())
    .map(([requirement_id, comment]) => ({ requirement_id, comment }))
  return entries.length > 0 ? entries : null
}

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
  const isAssignedReviewer =
    actor?.role === 'internal_collaborator' &&
    actor.membership_id === evaluation?.reviewer_membership_id

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet({ query: { enabled: isOwner } })
  const orgMembers = unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []
  const approvers = orgMembers.filter((member) => member.role === 'approver')
  const reviewers = orgMembers.filter((member) => member.role === 'internal_collaborator')
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
  const [changesRequested, setChangesRequested] = useState(false)
  const [requirementNotes, setRequirementNotes] = useState<Record<string, string>>({})

  const [selectedReviewerId, setSelectedReviewerId] = useState('')
  const [reviewComment, setReviewComment] = useState('')
  const [confirmWithdrawReview, setConfirmWithdrawReview] = useState(false)
  const [confirmReviewReject, setConfirmReviewReject] = useState(false)
  const [reviewChangesRequested, setReviewChangesRequested] = useState(false)
  const [reviewRequirementNotes, setReviewRequirementNotes] = useState<Record<string, string>>({})

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
        setChangesRequested(false)
        setRequirementNotes({})
      },
    },
  })

  const setReviewer = useSetReviewerApiV1EvaluationsEvaluationIdReviewerPost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const requestReview = useRequestReviewApiV1EvaluationsEvaluationIdRequestReviewPost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const withdrawReviewRequest =
    useWithdrawReviewRequestApiV1EvaluationsEvaluationIdRequestReviewDelete({
      mutation: {
        onSuccess: () => {
          invalidateEvaluation()
          setConfirmWithdrawReview(false)
        },
      },
    })
  const reviewApprove = useReviewApproveApiV1EvaluationsEvaluationIdReviewApprovePost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const reviewReject = useReviewRejectApiV1EvaluationsEvaluationIdReviewRejectPost({
    mutation: {
      onSuccess: () => {
        invalidateEvaluation()
        setConfirmReviewReject(false)
        setReviewComment('')
        setReviewChangesRequested(false)
        setReviewRequirementNotes({})
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

  const canConfigureReview =
    isOwner &&
    evaluation.status === 'draft' &&
    (evaluation.review_status === 'not_requested' || evaluation.review_status === 'rejected')
  const effectiveReviewerId = selectedReviewerId || evaluation.reviewer_membership_id
  const reviewRequestReasons = requestReviewPreconditionReasons({
    ...evaluation,
    reviewer_membership_id: effectiveReviewerId,
  })
  const canRequestReview = canConfigureReview && reviewRequestReasons.length === 0
  const reviewRequestPending = setReviewer.isPending || requestReview.isPending
  const reviewRequestError = setReviewer.isError
    ? setReviewer.error
    : requestReview.isError
      ? requestReview.error
      : null

  const handleRequestReview = async () => {
    try {
      const reviewerToSet = selectedReviewerId || evaluation.reviewer_membership_id
      if (reviewerToSet && reviewerToSet !== evaluation.reviewer_membership_id) {
        await setReviewer.mutateAsync({
          evaluationId: evaluation.id,
          data: { reviewer_membership_id: reviewerToSet },
        })
      }
      await requestReview.mutateAsync({ evaluationId: evaluation.id })
    } catch {
      // Surfaced via the individual mutations' own isError/error state above.
    }
  }

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
  const reviewRequestedByLabel = memberLabel(evaluation.review_requested_by_membership_id)
  const reviewDecidedByLabel = memberLabel(evaluation.review_decided_by_membership_id)

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {/* ADR 0026 (R2): the review stage is optional per evaluation - shown
          to the owner always (so they can opt in), and to everyone else
          only once a reviewer has actually been assigned. */}
      {(isOwner || evaluation.reviewer_membership_id) && (
        <section className="mt-6">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">Revisión (opcional)</h2>
            {evaluation.reviewer_membership_id && (
              <StatusBadge label={translateReviewStatus(evaluation.review_status)} />
            )}
          </div>

          {evaluation.reviewer_membership_id ? (
            <dl className="mt-3 grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Revisor</dt>
                <dd className="text-foreground">
                  {memberLabel(evaluation.reviewer_membership_id) ?? 'Desconocido'}
                </dd>
              </div>
              {evaluation.review_requested_at && (
                <div>
                  <dt className="text-muted-foreground">Solicitada</dt>
                  <dd className="text-foreground">
                    {new Date(evaluation.review_requested_at).toLocaleString()}
                    {reviewRequestedByLabel ? ` · ${reviewRequestedByLabel}` : ''}
                  </dd>
                </div>
              )}
              {evaluation.review_decided_at && (
                <div>
                  <dt className="text-muted-foreground">
                    {evaluation.review_status === 'rejected' ? 'Rechazada' : 'Decidida'}
                  </dt>
                  <dd className="text-foreground">
                    {new Date(evaluation.review_decided_at).toLocaleString()}
                    {reviewDecidedByLabel ? ` · ${reviewDecidedByLabel}` : ''}
                  </dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">
              Sin revisor asignado - esta evaluación puede pedir aprobación directamente.
            </p>
          )}
          {evaluation.review_comment && (
            <p className="mt-3 text-sm text-muted-foreground">
              Comentario: {evaluation.review_comment}
            </p>
          )}

          {canConfigureReview && (
            <div className="mt-4 flex flex-col gap-3">
              <div>
                <Label htmlFor="review-reviewer-select">Revisor</Label>
                <Select
                  value={selectedReviewerId || evaluation.reviewer_membership_id || undefined}
                  onValueChange={setSelectedReviewerId}
                >
                  <SelectTrigger id="review-reviewer-select" className="w-full">
                    <SelectValue placeholder="Selecciona un revisor" />
                  </SelectTrigger>
                  <SelectContent>
                    {reviewers.length === 0 ? (
                      <SelectItem value="" disabled>
                        Sin colaboradores internos en tu organización
                      </SelectItem>
                    ) : (
                      reviewers.map((member) => (
                        <SelectItem key={member.membership_id} value={member.membership_id}>
                          {member.display_name}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>
              {reviewRequestError && (
                <ErrorBanner message={normalizeApiError(reviewRequestError).message} />
              )}
              <Button
                type="button"
                variant="outline"
                className="self-start"
                disabled={!canRequestReview || reviewRequestPending}
                onClick={handleRequestReview}
              >
                {reviewRequestPending ? 'Solicitando…' : 'Solicitar revisión'}
              </Button>
              <DisabledActionHint reasons={canRequestReview ? [] : reviewRequestReasons} />
            </div>
          )}

          {isOwner && evaluation.review_status === 'pending' && (
            <div className="mt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setConfirmWithdrawReview(true)}
              >
                Retirar solicitud de revisión
              </Button>
            </div>
          )}

          {isAssignedReviewer && evaluation.review_status === 'pending' && (
            <div className="mt-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-foreground">Tu revisión</h3>
              <div>
                <Label htmlFor="review-comment">Comentario (obligatorio para rechazar)</Label>
                <Textarea
                  id="review-comment"
                  value={reviewComment}
                  onChange={(event) => setReviewComment(event.target.value)}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="review-changes-requested"
                  checked={reviewChangesRequested}
                  onCheckedChange={() => setReviewChangesRequested((value) => !value)}
                />
                <Label htmlFor="review-changes-requested" className="text-sm">
                  Es una solicitud de cambios, no un rechazo definitivo
                </Label>
              </div>
              {reviewChangesRequested && (
                <RequirementNotesEditor
                  requirements={evaluation.requirements}
                  notes={reviewRequirementNotes}
                  onChange={(id, value) =>
                    setReviewRequirementNotes((prev) => ({ ...prev, [id]: value }))
                  }
                />
              )}
              {(reviewApprove.isError || reviewReject.isError) && (
                <ErrorBanner
                  message={normalizeApiError(reviewApprove.error ?? reviewReject.error).message}
                />
              )}
              <div className="flex gap-2">
                <Button
                  type="button"
                  disabled={reviewApprove.isPending}
                  onClick={() =>
                    reviewApprove.mutate({
                      evaluationId: evaluation.id,
                      data: { comment: reviewComment || null },
                    })
                  }
                >
                  {reviewApprove.isPending ? 'Aprobando…' : 'Aprobar revisión'}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={!reviewComment.trim()}
                  onClick={() => setConfirmReviewReject(true)}
                >
                  {reviewChangesRequested ? 'Solicitar cambios' : 'Rechazar'}
                </Button>
              </div>
              <DisabledActionHint
                reasons={
                  reviewComment.trim() ? [] : ['Debes escribir un comentario para rechazar.']
                }
              />
            </div>
          )}
        </section>
      )}

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
                onValueChange={(value) => {
                  setSelectedApproverId(value)
                  // ADR 0026 (R2): persist immediately rather than only as
                  // part of the "Solicitar aprobación" submit - that button
                  // can now stay disabled purely because review hasn't
                  // passed yet (a reason unrelated to whether an approver
                  // is chosen), so waiting for it would make the approver
                  // impossible to configure in advance while review is in
                  // progress, defeating the auto-chain on review approval.
                  if (value && value !== evaluation.approver_membership_id) {
                    setApprover.mutate({
                      evaluationId: evaluation.id,
                      data: { approver_membership_id: value },
                    })
                  }
                }}
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
                onBlur={(event) => {
                  const value = event.target.value
                  const deadlineIso = value ? new Date(`${value}T00:00:00Z`).toISOString() : null
                  // Same reasoning as the approver Select above - persisted
                  // on blur, not gated behind the request-approval button.
                  if (deadlineIso && deadlineIso !== evaluation.response_deadline) {
                    updateDeadline.mutate({
                      evaluationId: evaluation.id,
                      data: { response_deadline: deadlineIso },
                    })
                  }
                }}
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
            <div className="flex items-center gap-2">
              <Checkbox
                id="approval-changes-requested"
                checked={changesRequested}
                onCheckedChange={() => setChangesRequested((value) => !value)}
              />
              <Label htmlFor="approval-changes-requested" className="text-sm">
                Es una solicitud de cambios, no un rechazo definitivo
              </Label>
            </div>
            {changesRequested && (
              <RequirementNotesEditor
                requirements={evaluation.requirements}
                notes={requirementNotes}
                onChange={(id, value) => setRequirementNotes((prev) => ({ ...prev, [id]: value }))}
              />
            )}
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
                {changesRequested ? 'Solicitar cambios' : 'Rechazar'}
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
        title={changesRequested ? 'Solicitar cambios' : 'Rechazar evaluación'}
        description="El responsable de evaluación verá tu comentario y podrá editar y volver a solicitar aprobación."
        confirmLabel={changesRequested ? 'Solicitar cambios' : 'Rechazar'}
        variant="destructive"
        isPending={rejectEvaluation.isPending}
        onConfirm={() =>
          rejectEvaluation.mutate({
            evaluationId: evaluation.id,
            data: {
              comment,
              kind: changesRequested ? 'changes_requested' : 'rejected',
              requirement_notes: buildRequirementNotes(requirementNotes),
            },
          })
        }
      />

      <ConfirmDialog
        open={confirmWithdrawReview}
        onOpenChange={setConfirmWithdrawReview}
        title="Retirar solicitud de revisión"
        description="El revisor ya no podrá decidir sobre esta solicitud hasta que la vuelvas a enviar."
        confirmLabel="Retirar solicitud"
        variant="destructive"
        isPending={withdrawReviewRequest.isPending}
        onConfirm={() => withdrawReviewRequest.mutate({ evaluationId: evaluation.id })}
      />

      <ConfirmDialog
        open={confirmReviewReject}
        onOpenChange={setConfirmReviewReject}
        title={reviewChangesRequested ? 'Solicitar cambios' : 'Rechazar revisión'}
        description="El responsable de evaluación verá tu comentario y podrá editar y volver a solicitar revisión."
        confirmLabel={reviewChangesRequested ? 'Solicitar cambios' : 'Rechazar'}
        variant="destructive"
        isPending={reviewReject.isPending}
        onConfirm={() =>
          reviewReject.mutate({
            evaluationId: evaluation.id,
            data: {
              comment: reviewComment,
              kind: reviewChangesRequested ? 'changes_requested' : 'rejected',
              requirement_notes: buildRequirementNotes(reviewRequirementNotes),
            },
          })
        }
      />
    </div>
  )
}
