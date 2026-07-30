import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGetQueryKey,
  useCreateAssignmentApiV1EvaluationsEvaluationIdAssignmentsPost,
  useDeleteAssignmentApiV1EvaluationsEvaluationIdAssignmentsAssignmentIdDelete,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGet,
  useListOrgMembersApiV1OrgMembersGet,
  useUpdateAssignmentStatusApiV1EvaluationsEvaluationIdAssignmentsAssignmentIdStatusPatch,
  type AssignmentListResponse,
  type AssignmentResponseDimension,
  type AssignmentResponseStatus,
  type EvaluationDetailResponse,
  type OrgMembersListResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
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
  translateAssignmentStatus,
  translateDimension,
  translateEvaluationStatus,
} from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'

// Mirrors procurawise.shared.roles.EVALUATOR_ROLE_BY_DIMENSION - which
// evaluator sub-role may be assigned to which dimension's sections.
const EVALUATOR_ROLE_BY_DIMENSION: Record<string, string> = {
  functional: 'evaluator_functional',
  technical: 'evaluator_technical',
}

export function AssignmentsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const assignmentsQuery = useListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGet(
    evaluationId!,
  )
  const assignments = unwrapData<AssignmentListResponse>(assignmentsQuery.data)?.items ?? []

  const orgMembersQuery = useListOrgMembersApiV1OrgMembersGet({ query: { enabled: isOwner } })
  const orgMembers = unwrapData<OrgMembersListResponse>(orgMembersQuery.data)?.items ?? []

  const [selectedSection, setSelectedSection] = useState('')
  const [selectedEvaluatorId, setSelectedEvaluatorId] = useState('')
  const [pendingDelete, setPendingDelete] = useState<{ id: string; section: string } | null>(null)

  const invalidateAssignments = () =>
    queryClient.invalidateQueries({
      queryKey: getListAssignmentsApiV1EvaluationsEvaluationIdAssignmentsGetQueryKey(evaluationId),
    })

  const createAssignment = useCreateAssignmentApiV1EvaluationsEvaluationIdAssignmentsPost({
    mutation: {
      onSuccess: () => {
        invalidateAssignments()
        setSelectedSection('')
        setSelectedEvaluatorId('')
      },
    },
  })
  const updateStatus =
    useUpdateAssignmentStatusApiV1EvaluationsEvaluationIdAssignmentsAssignmentIdStatusPatch({
      mutation: { onSuccess: invalidateAssignments },
    })
  const deleteAssignment =
    useDeleteAssignmentApiV1EvaluationsEvaluationIdAssignmentsAssignmentIdDelete({
      mutation: { onSuccess: invalidateAssignments },
    })

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando asignaciones…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  // Every distinct (dimension, category) pair actually present on this
  // evaluation's requirements - an Assignment can only ever reference one of
  // these (backend: SectionNotFoundError otherwise).
  const sections = Array.from(
    new Map(evaluation.requirements.map((r) => [`${r.dimension}::${r.category}`, r])).values(),
  )

  const [sectionDimension, sectionName] = selectedSection.split('::')
  const expectedRole = sectionDimension ? EVALUATOR_ROLE_BY_DIMENSION[sectionDimension] : undefined
  const eligibleEvaluators = orgMembers.filter((m) => m.role === expectedRole)

  const membersById = new Map(orgMembers.map((m) => [m.membership_id, m]))
  const evaluatorLabel = (membershipId: string) =>
    membersById.get(membershipId)?.display_name ?? membershipId

  const canSubmit = Boolean(selectedSection && selectedEvaluatorId)

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">Asignaciones por sección</h2>

        {assignmentsQuery.isLoading && <LoadingState label="Cargando asignaciones…" />}
        {assignmentsQuery.error && (
          <ErrorBanner message={normalizeApiError(assignmentsQuery.error).message} />
        )}
        {!assignmentsQuery.isLoading && assignments.length === 0 && (
          <div className="mt-2">
            <EmptyState title="Ninguna sección asignada todavía" />
          </div>
        )}
        {assignments.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dimensión</TableHead>
                  <TableHead>Sección</TableHead>
                  <TableHead>Evaluador</TableHead>
                  <TableHead>Progreso</TableHead>
                  <TableHead>Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignments.map((assignment) => {
                  const canUpdateStatus =
                    isOwner || actor?.membership_id === assignment.evaluator_membership_id
                  return (
                    <TableRow key={assignment.id}>
                      <TableCell>{translateDimension(assignment.dimension)}</TableCell>
                      <TableCell>{assignment.section}</TableCell>
                      <TableCell>{evaluatorLabel(assignment.evaluator_membership_id)}</TableCell>
                      <TableCell>
                        {canUpdateStatus ? (
                          <Select
                            value={assignment.status}
                            onValueChange={(value) =>
                              updateStatus.mutate({
                                evaluationId: evaluation.id,
                                assignmentId: assignment.id,
                                data: { status: value as AssignmentResponseStatus },
                              })
                            }
                          >
                            <SelectTrigger size="sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="not_started">
                                {translateAssignmentStatus('not_started')}
                              </SelectItem>
                              <SelectItem value="in_progress">
                                {translateAssignmentStatus('in_progress')}
                              </SelectItem>
                              <SelectItem value="completed">
                                {translateAssignmentStatus('completed')}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        ) : (
                          <StatusBadge label={translateAssignmentStatus(assignment.status)} />
                        )}
                      </TableCell>
                      <TableCell>
                        {isOwner && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              setPendingDelete({ id: assignment.id, section: assignment.section })
                            }
                          >
                            Quitar
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {isOwner && (
        <section className="mt-6 max-w-lg">
          <h2 className="text-sm font-semibold text-foreground">Asignar evaluador a sección</h2>
          {sections.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">
              Agrega requerimientos antes de poder asignar secciones.
            </p>
          ) : (
            <div className="mt-2 flex flex-col gap-3">
              {createAssignment.isError && (
                <ErrorBanner message={normalizeApiError(createAssignment.error).message} />
              )}
              <Select
                value={selectedSection}
                onValueChange={(value) => {
                  setSelectedSection(value)
                  setSelectedEvaluatorId('')
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecciona una sección" />
                </SelectTrigger>
                <SelectContent>
                  {sections.map((requirement) => (
                    <SelectItem
                      key={`${requirement.dimension}::${requirement.category}`}
                      value={`${requirement.dimension}::${requirement.category}`}
                    >
                      {translateDimension(requirement.dimension)} · {requirement.category}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={selectedEvaluatorId}
                onValueChange={setSelectedEvaluatorId}
                disabled={!selectedSection}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecciona un evaluador" />
                </SelectTrigger>
                <SelectContent>
                  {eligibleEvaluators.length === 0 ? (
                    <SelectItem value="" disabled>
                      Sin evaluadores de este rol en tu organización
                    </SelectItem>
                  ) : (
                    eligibleEvaluators.map((member) => (
                      <SelectItem key={member.membership_id} value={member.membership_id}>
                        {member.display_name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>

              <Button
                type="button"
                className="self-start"
                disabled={!canSubmit || createAssignment.isPending}
                onClick={() =>
                  createAssignment.mutate({
                    evaluationId: evaluation.id,
                    data: {
                      dimension: sectionDimension as AssignmentResponseDimension,
                      section: sectionName,
                      evaluator_membership_id: selectedEvaluatorId,
                    },
                  })
                }
              >
                {createAssignment.isPending ? 'Asignando…' : 'Asignar'}
              </Button>
            </div>
          )}
        </section>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Quitar asignación"
        description={`Se quitará la asignación de la sección "${pendingDelete?.section ?? ''}".`}
        confirmLabel="Quitar"
        variant="destructive"
        isPending={deleteAssignment.isPending}
        onConfirm={() => {
          if (!pendingDelete) return
          deleteAssignment.mutate(
            { evaluationId: evaluation.id, assignmentId: pendingDelete.id },
            { onSuccess: () => setPendingDelete(null) },
          )
        }}
      />
    </div>
  )
}
