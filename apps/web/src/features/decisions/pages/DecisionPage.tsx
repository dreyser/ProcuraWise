import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetDecisionApiV1EvaluationsEvaluationIdDecisionGetQueryKey,
  getGetReadinessApiV1EvaluationsEvaluationIdDecisionReadinessGetQueryKey,
  useApproveDecisionApiV1EvaluationsEvaluationIdDecisionApprovePost,
  useCreateDecisionApiV1EvaluationsEvaluationIdDecisionPost,
  useGetDecisionApiV1EvaluationsEvaluationIdDecisionGet,
  useGetDecisionSnapshotApiV1EvaluationsEvaluationIdDecisionSnapshotGet,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useGetReadinessApiV1EvaluationsEvaluationIdDecisionReadinessGet,
  useGetResultsApiV1EvaluationsEvaluationIdResultsGet,
  useListOrgMembersApiV1OrgMembersGet,
  useRejectDecisionApiV1EvaluationsEvaluationIdDecisionRejectPost,
  useRequestDecisionApprovalApiV1EvaluationsEvaluationIdDecisionRequestApprovalPost,
  useSetDecisionApproverApiV1EvaluationsEvaluationIdDecisionApproverPost,
  useUpdateDecisionApiV1EvaluationsEvaluationIdDecisionPatch,
  useWithdrawDecisionApprovalRequestApiV1EvaluationsEvaluationIdDecisionRequestApprovalDelete,
  type DecisionReadinessResponse,
  type DecisionResponse,
  type DecisionSnapshotResponse,
  type EvaluationDetailResponse,
  type OrgMembersListResponse,
  type ResultsResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  translateDecisionOutcome,
  translateDecisionStatus,
  translateEvaluationStatus,
} from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'

/** "Decisión" tab (Fase 22, plan Bloqueante #1 Opcion B): the decision's own
 * approver is a separate assignment from the evaluation's publication
 * approver (Fase 12) - never copied automatically, only ever set via an
 * explicit owner action on this page. Only reachable once
 * Evaluation.status === "completed" (plan section 10, decision 1); the
 * results table shown here reuses the same disclaimer text as ResultsPage
 * ("no es un ranking ni implica adjudicación") so the human-in-the-loop
 * principle stays visible at the exact moment a selection is made. */
export function DecisionPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)
  const isCompleted = evaluation?.status === 'completed'

  const readinessQuery = useGetReadinessApiV1EvaluationsEvaluationIdDecisionReadinessGet(
    evaluationId!,
    { query: { enabled: isCompleted } },
  )
  const readiness = unwrapData<DecisionReadinessResponse>(readinessQuery.data)

  const decisionQuery = useGetDecisionApiV1EvaluationsEvaluationIdDecisionGet(evaluationId!, {
    query: { enabled: isCompleted, retry: false },
  })
  const decision =
    decisionQuery.error instanceof ApiError && decisionQuery.error.status === 404
      ? undefined
      : unwrapData<DecisionResponse>(decisionQuery.data)

  const resultsQuery = useGetResultsApiV1EvaluationsEvaluationIdResultsGet(evaluationId!, {
    query: { enabled: isCompleted },
  })
  const results = unwrapData<ResultsResponse>(resultsQuery.data)

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet({ query: { enabled: isOwner } })
  const orgMembers = unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []
  const approvers = orgMembers.filter((member) => member.role === 'approver')
  const memberLabel = (membershipId: string | null): string | null => {
    if (!membershipId) return null
    return orgMembers.find((member) => member.membership_id === membershipId)?.display_name ?? null
  }

  const isAssignedDecisionApprover =
    actor?.role === 'approver' && actor.membership_id === decision?.approver_membership_id

  const snapshotQuery = useGetDecisionSnapshotApiV1EvaluationsEvaluationIdDecisionSnapshotGet(
    evaluationId!,
    { query: { enabled: decision?.status === 'approved' } },
  )
  const snapshot =
    decision?.status === 'approved'
      ? unwrapData<DecisionSnapshotResponse>(snapshotQuery.data)
      : undefined

  const [outcome, setOutcome] = useState('')
  const [selectedVendorOrgId, setSelectedVendorOrgId] = useState('')
  const [voidReason, setVoidReason] = useState('')
  const [justification, setJustification] = useState('')
  const [selectedApproverId, setSelectedApproverId] = useState('')
  const [rejectComment, setRejectComment] = useState('')
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)

  const invalidateDecision = () => {
    queryClient.invalidateQueries({
      queryKey: getGetDecisionApiV1EvaluationsEvaluationIdDecisionGetQueryKey(evaluationId),
    })
    queryClient.invalidateQueries({
      queryKey:
        getGetReadinessApiV1EvaluationsEvaluationIdDecisionReadinessGetQueryKey(evaluationId),
    })
  }

  const createDecision = useCreateDecisionApiV1EvaluationsEvaluationIdDecisionPost({
    mutation: { onSuccess: invalidateDecision },
  })
  const updateDecision = useUpdateDecisionApiV1EvaluationsEvaluationIdDecisionPatch({
    mutation: { onSuccess: invalidateDecision },
  })
  const setDecisionApprover =
    useSetDecisionApproverApiV1EvaluationsEvaluationIdDecisionApproverPost({
      mutation: { onSuccess: invalidateDecision },
    })
  const requestDecisionApproval =
    useRequestDecisionApprovalApiV1EvaluationsEvaluationIdDecisionRequestApprovalPost({
      mutation: { onSuccess: invalidateDecision },
    })
  const withdrawDecisionApprovalRequest =
    useWithdrawDecisionApprovalRequestApiV1EvaluationsEvaluationIdDecisionRequestApprovalDelete({
      mutation: {
        onSuccess: () => {
          invalidateDecision()
          setConfirmWithdraw(false)
        },
      },
    })
  const approveDecision = useApproveDecisionApiV1EvaluationsEvaluationIdDecisionApprovePost({
    mutation: { onSuccess: invalidateDecision },
  })
  const rejectDecision = useRejectDecisionApiV1EvaluationsEvaluationIdDecisionRejectPost({
    mutation: {
      onSuccess: () => {
        invalidateDecision()
        setConfirmReject(false)
        setRejectComment('')
      },
    },
  })

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando decisión…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  if (!isCompleted) {
    return (
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
          <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
        </div>
        <EvaluationTabNav evaluationId={evaluation.id} />
        <p className="mt-6 text-sm text-muted-foreground">
          La decisión estará disponible cuando la evaluación esté completada.
        </p>
      </div>
    )
  }

  const canEdit =
    isOwner && (!decision || decision.status === 'not_requested' || decision.status === 'rejected')
  const effectiveOutcome = outcome || decision?.outcome || ''
  const effectiveVendorOrgId = selectedVendorOrgId || decision?.selected_vendor_org_id || ''
  const effectiveJustification = justification || decision?.justification || ''
  const effectiveApproverId =
    selectedApproverId ||
    decision?.approver_membership_id ||
    readiness?.suggested_approver_membership_id ||
    ''

  // Client-side preview against the locally-selected outcome/vendor/
  // justification/approver, not just the last-persisted server values
  // (same "preview the pending local edit" principle as
  // evaluationReadiness.ts's requestApprovalPreconditionReasons) - the
  // approver assignment itself only happens inside handleRequestApproval
  // below, so gating the button on the server's readiness alone (which only
  // reflects already-persisted state) would make it impossible to ever
  // click for the first time.
  const requestReasons: string[] = []
  if (!effectiveOutcome) {
    requestReasons.push('Debes elegir un resultado (proveedor seleccionado o desierto).')
  } else if (effectiveOutcome === 'selected' && !effectiveVendorOrgId) {
    requestReasons.push('Debes seleccionar un proveedor.')
  } else if (effectiveOutcome === 'void' && !(voidReason || decision?.void_reason)) {
    requestReasons.push('Debes indicar el motivo de declarar desierto.')
  }
  if (!effectiveJustification || effectiveJustification.trim().length < 20) {
    requestReasons.push('La justificación debe tener al menos 20 caracteres.')
  }
  if (!effectiveApproverId) {
    requestReasons.push('Debes asignar un aprobador de la decisión.')
  }
  const canRequestApproval = canEdit && requestReasons.length === 0

  const handleSaveSelection = () => {
    updateDecision.mutate({
      evaluationId: evaluation.id,
      data: {
        outcome: (effectiveOutcome || null) as 'selected' | 'void' | null,
        selected_vendor_org_id:
          effectiveOutcome === 'selected' ? effectiveVendorOrgId || null : null,
        void_reason:
          effectiveOutcome === 'void' ? voidReason || decision?.void_reason || null : null,
        justification: effectiveJustification || null,
      },
    })
  }

  const handleRequestApproval = async () => {
    try {
      if (effectiveApproverId && effectiveApproverId !== decision?.approver_membership_id) {
        await setDecisionApprover.mutateAsync({
          evaluationId: evaluation.id,
          data: { approver_membership_id: effectiveApproverId },
        })
      }
      await requestDecisionApproval.mutateAsync({ evaluationId: evaluation.id })
    } catch {
      // Surfaced via the individual mutations' own isError/error state below.
    }
  }

  const requestedByLabel = memberLabel(decision?.approval_requested_by_membership_id ?? null)
  const decidedByLabel = memberLabel(decision?.approval_decided_by_membership_id ?? null)
  const decisionApproverLabel = memberLabel(decision?.approver_membership_id ?? null)

  const requestPending =
    setDecisionApprover.isPending || requestDecisionApproval.isPending || createDecision.isPending
  const requestError = setDecisionApprover.isError
    ? setDecisionApprover.error
    : requestDecisionApproval.isError
      ? requestDecisionApproval.error
      : createDecision.isError
        ? createDecision.error
        : null

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {results && results.proposals.length > 0 && (
        <section className="mt-6">
          <h2 className="text-sm font-semibold text-foreground">Resultados de referencia</h2>
          <div className="mt-3 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Resultado final</TableHead>
                  <TableHead>Alertas obligatorias</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.proposals.map((proposal) => (
                  <TableRow key={proposal.proposal_id}>
                    <TableCell>{proposal.vendor_org_name}</TableCell>
                    <TableCell>
                      {proposal.final_result
                        ? `${proposal.final_result.total_points} / ${proposal.final_result.maximum_points}`
                        : 'No disponible'}
                    </TableCell>
                    <TableCell>{proposal.mandatory_alerts_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="px-4 py-2 text-xs text-muted-foreground">
              Orden estable por proveedor - no es un ranking ni implica adjudicación. La selección
              final siempre es una decisión humana explícita.
            </p>
          </div>
        </section>
      )}

      {!decision && isOwner && (
        <section className="mt-6">
          {requestError && <ErrorBanner message={normalizeApiError(requestError).message} />}
          <Button
            type="button"
            disabled={createDecision.isPending}
            onClick={() => createDecision.mutate({ evaluationId: evaluation.id })}
          >
            {createDecision.isPending ? 'Creando…' : 'Iniciar decisión'}
          </Button>
        </section>
      )}

      {decision && (
        <>
          <section className="mt-6">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-foreground">Estado de la decisión</h2>
              <StatusBadge label={translateDecisionStatus(decision.status)} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Aprobador de la decisión</dt>
                <dd className="text-foreground">{decisionApproverLabel ?? 'Sin asignar'}</dd>
              </div>
              {decision.approval_requested_at && (
                <div>
                  <dt className="text-muted-foreground">Solicitada</dt>
                  <dd className="text-foreground">
                    {new Date(decision.approval_requested_at).toLocaleString()}
                    {requestedByLabel ? ` · ${requestedByLabel}` : ''}
                  </dd>
                </div>
              )}
              {decision.approval_decided_at && (
                <div>
                  <dt className="text-muted-foreground">
                    {decision.status === 'rejected' ? 'Rechazada' : 'Decidida'}
                  </dt>
                  <dd className="text-foreground">
                    {new Date(decision.approval_decided_at).toLocaleString()}
                    {decidedByLabel ? ` · ${decidedByLabel}` : ''}
                  </dd>
                </div>
              )}
            </dl>
            {decision.approval_comment && (
              <p className="mt-3 text-sm text-muted-foreground">
                Comentario: {decision.approval_comment}
              </p>
            )}
          </section>

          {canEdit && (
            <section className="mt-6">
              <h2 className="text-sm font-semibold text-foreground">Selección y justificación</h2>
              <div className="mt-3 flex flex-col gap-3">
                <div>
                  <Label htmlFor="decision-outcome-select">Resultado</Label>
                  <Select value={effectiveOutcome || undefined} onValueChange={setOutcome}>
                    <SelectTrigger id="decision-outcome-select" className="w-full">
                      <SelectValue placeholder="Selecciona una opción" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="selected">
                        {translateDecisionOutcome('selected')}
                      </SelectItem>
                      <SelectItem value="void">{translateDecisionOutcome('void')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {effectiveOutcome === 'selected' && (
                  <div>
                    <Label htmlFor="decision-vendor-select">Proveedor seleccionado</Label>
                    <Select
                      value={effectiveVendorOrgId || undefined}
                      onValueChange={setSelectedVendorOrgId}
                    >
                      <SelectTrigger id="decision-vendor-select" className="w-full">
                        <SelectValue placeholder="Selecciona un proveedor" />
                      </SelectTrigger>
                      <SelectContent>
                        {(results?.proposals ?? []).map((proposal) => (
                          <SelectItem key={proposal.vendor_org_id} value={proposal.vendor_org_id}>
                            {proposal.vendor_org_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {effectiveOutcome === 'void' && (
                  <div>
                    <Label htmlFor="decision-void-reason">Motivo de declarar desierto</Label>
                    <Textarea
                      id="decision-void-reason"
                      defaultValue={decision.void_reason ?? ''}
                      onChange={(event) => setVoidReason(event.target.value)}
                    />
                  </div>
                )}

                <div>
                  <Label htmlFor="decision-justification">Justificación</Label>
                  <Textarea
                    id="decision-justification"
                    defaultValue={decision.justification ?? ''}
                    onChange={(event) => setJustification(event.target.value)}
                  />
                </div>

                {updateDecision.isError && (
                  <ErrorBanner message={normalizeApiError(updateDecision.error).message} />
                )}
                <Button
                  type="button"
                  className="self-start"
                  variant="outline"
                  disabled={updateDecision.isPending || !effectiveOutcome}
                  onClick={handleSaveSelection}
                >
                  {updateDecision.isPending ? 'Guardando…' : 'Guardar selección'}
                </Button>
              </div>
            </section>
          )}

          {canEdit && (
            <section className="mt-6">
              <h2 className="text-sm font-semibold text-foreground">Solicitar aprobación</h2>
              <div className="mt-3 flex flex-col gap-3">
                <div>
                  <Label htmlFor="decision-approver-select">Aprobador de la decisión</Label>
                  <Select
                    value={effectiveApproverId || undefined}
                    onValueChange={setSelectedApproverId}
                  >
                    <SelectTrigger id="decision-approver-select" className="w-full">
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
                  <p className="mt-1 text-xs text-muted-foreground">
                    Puede ser la misma persona que aprobó la publicación, u otra distinta - esta
                    asignación es independiente y no se copia automáticamente.
                  </p>
                </div>
                {requestError && <ErrorBanner message={normalizeApiError(requestError).message} />}
                <Button
                  type="button"
                  className="self-start"
                  disabled={requestPending || !canRequestApproval}
                  onClick={handleRequestApproval}
                >
                  {requestPending ? 'Solicitando…' : 'Solicitar aprobación'}
                </Button>
                <DisabledActionHint reasons={canRequestApproval ? [] : requestReasons} />
              </div>
            </section>
          )}

          {isOwner && decision.status === 'pending' && (
            <section className="mt-6">
              <Button type="button" variant="outline" onClick={() => setConfirmWithdraw(true)}>
                Retirar solicitud
              </Button>
            </section>
          )}

          {isAssignedDecisionApprover && decision.status === 'pending' && (
            <section className="mt-6 max-w-lg">
              <h2 className="text-sm font-semibold text-foreground">Tu decisión</h2>
              <div className="mt-3 flex flex-col gap-3">
                <div>
                  <Label htmlFor="decision-approval-comment">
                    Comentario (obligatorio para rechazar)
                  </Label>
                  <Textarea
                    id="decision-approval-comment"
                    value={rejectComment}
                    onChange={(event) => setRejectComment(event.target.value)}
                  />
                </div>
                {(approveDecision.isError || rejectDecision.isError) && (
                  <ErrorBanner
                    message={
                      normalizeApiError(approveDecision.error ?? rejectDecision.error).message
                    }
                  />
                )}
                <div className="flex gap-2">
                  <Button
                    type="button"
                    disabled={approveDecision.isPending}
                    onClick={() =>
                      approveDecision.mutate({
                        evaluationId: evaluation.id,
                        data: { comment: rejectComment || null },
                      })
                    }
                  >
                    {approveDecision.isPending ? 'Aprobando…' : 'Aprobar'}
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    disabled={!rejectComment.trim()}
                    onClick={() => setConfirmReject(true)}
                  >
                    Rechazar
                  </Button>
                </div>
                <DisabledActionHint
                  reasons={
                    rejectComment.trim() ? [] : ['Debes escribir un comentario para rechazar.']
                  }
                />
              </div>
            </section>
          )}

          {decision.status === 'approved' && (
            <section className="mt-6">
              <h2 className="text-sm font-semibold text-foreground">Memo de cierre</h2>
              {snapshotQuery.isLoading && <LoadingState label="Cargando memo de cierre…" />}
              {snapshotQuery.error && (
                <ErrorBanner message={normalizeApiError(snapshotQuery.error).message} />
              )}
              {snapshot && (
                <div className="mt-3 rounded-md border border-border p-4 text-sm">
                  <p>
                    <span className="font-medium text-foreground">Resultado: </span>
                    {translateDecisionOutcome(snapshot.outcome)}
                    {snapshot.selected_vendor_org_name
                      ? ` — ${snapshot.selected_vendor_org_name}`
                      : ''}
                  </p>
                  {snapshot.void_reason && (
                    <p className="mt-2">
                      <span className="font-medium text-foreground">Motivo: </span>
                      {snapshot.void_reason}
                    </p>
                  )}
                  <p className="mt-2">
                    <span className="font-medium text-foreground">Justificación: </span>
                    {snapshot.justification}
                  </p>
                  <p className="mt-2 text-muted-foreground">
                    Aprobada el {new Date(snapshot.decided_at).toLocaleString()} por{' '}
                    {memberLabel(snapshot.approver_membership_id) ??
                      snapshot.approver_membership_id}
                    . Este memo quedó congelado de forma permanente y es de solo lectura.
                  </p>
                </div>
              )}
            </section>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmWithdraw}
        onOpenChange={setConfirmWithdraw}
        title="Retirar solicitud de aprobación"
        description="El aprobador de la decisión ya no podrá decidir hasta que la vuelvas a enviar."
        confirmLabel="Retirar solicitud"
        variant="destructive"
        isPending={withdrawDecisionApprovalRequest.isPending}
        onConfirm={() => withdrawDecisionApprovalRequest.mutate({ evaluationId: evaluation.id })}
      />

      <ConfirmDialog
        open={confirmReject}
        onOpenChange={setConfirmReject}
        title="Rechazar decisión"
        description="El responsable de evaluación verá tu comentario y podrá editar y volver a solicitar aprobación."
        confirmLabel="Rechazar"
        variant="destructive"
        isPending={rejectDecision.isPending}
        onConfirm={() =>
          rejectDecision.mutate({ evaluationId: evaluation.id, data: { comment: rejectComment } })
        }
      />
    </div>
  )
}
