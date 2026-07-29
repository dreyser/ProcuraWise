import { Fragment, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useAddRequirementApiV1EvaluationsEvaluationIdRequirementsPost,
  useDeleteRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdDelete,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useUpdateRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdPatch,
  type EvaluationDetailResponse,
  type RequirementResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { PriorityBadge } from '@/components/PriorityBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateEvaluationStatus, translateResponseType } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import { WeightSummary } from '@/features/evaluations/components/WeightSummary'
import {
  RequirementForm,
  type RequirementSubmitPayload,
} from '@/features/evaluations/components/RequirementForm'

type Dimension = 'functional' | 'technical'
type FormTarget =
  { mode: 'create'; dimension: Dimension } | { mode: 'edit'; requirement: RequirementResponse }

export function RequirementsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(data)

  const [formTarget, setFormTarget] = useState<FormTarget | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [orderDraft, setOrderDraft] = useState<Record<string, string>>({})

  const invalidateEvaluation = () =>
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
    })

  const addRequirement = useAddRequirementApiV1EvaluationsEvaluationIdRequirementsPost({
    mutation: { onSuccess: invalidateEvaluation },
  })
  const updateRequirement =
    useUpdateRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdPatch({
      mutation: { onSuccess: invalidateEvaluation },
    })
  const deleteRequirement =
    useDeleteRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdDelete({
      mutation: { onSuccess: invalidateEvaluation },
    })

  if (isLoading) return <LoadingState label="Cargando requerimientos…" />
  if (error instanceof ApiError && error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (error) return <ErrorBanner message={normalizeApiError(error).message} />
  if (!evaluation) return null

  const canEdit = isOwner && evaluation.status === 'draft'
  const byDimension = (dimension: Dimension) =>
    evaluation.requirements
      .filter((r) => r.dimension === dimension)
      .sort((a, b) => a.display_order - b.display_order)
  const weightOf = (dimension: Dimension) =>
    evaluation.requirements
      .filter((r) => r.dimension === dimension)
      .reduce((sum, r) => sum + r.weight, 0)

  const handleCreate = async (payload: RequirementSubmitPayload) => {
    await addRequirement.mutateAsync({ evaluationId: evaluation.id, data: payload })
    setFormTarget(null)
  }

  const handleUpdate = async (requirementId: string, payload: RequirementSubmitPayload) => {
    await updateRequirement.mutateAsync({
      evaluationId: evaluation.id,
      requirementId,
      data: payload,
    })
    setFormTarget(null)
  }

  const handleOrderCommit = (requirement: RequirementResponse) => {
    const raw = orderDraft[requirement.id]
    if (raw === undefined) return
    const parsed = Number(raw)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed === requirement.display_order) {
      setOrderDraft((prev) => {
        const next = { ...prev }
        delete next[requirement.id]
        return next
      })
      return
    }
    updateRequirement.mutate({
      evaluationId: evaluation.id,
      requirementId: requirement.id,
      data: { display_order: parsed },
    })
    setOrderDraft((prev) => {
      const next = { ...prev }
      delete next[requirement.id]
      return next
    })
  }

  const renderDimension = (dimension: Dimension, title: string) => {
    const requirements = byDimension(dimension)
    return (
      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {canEdit && formTarget?.mode !== 'create' && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setFormTarget({ mode: 'create', dimension })}
            >
              Agregar requerimiento
            </Button>
          )}
        </div>
        <WeightSummary dimension={dimension} currentWeight={weightOf(dimension)} />

        {formTarget?.mode === 'create' && formTarget.dimension === dimension && (
          <div className="mt-2">
            <RequirementForm
              defaultDimension={dimension}
              nextDisplayOrder={requirements.length + 1}
              onSubmit={handleCreate}
              onCancel={() => setFormTarget(null)}
              isSubmitting={addRequirement.isPending}
              submitError={addRequirement.error}
            />
          </div>
        )}

        {requirements.length === 0 && formTarget?.mode !== 'create' && (
          <div className="mt-2">
            <EmptyState title="Sin requerimientos en esta dimensión" />
          </div>
        )}

        {requirements.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Orden</TableHead>
                  <TableHead>Categoría</TableHead>
                  <TableHead>Título</TableHead>
                  <TableHead>Prioridad</TableHead>
                  <TableHead>Tipo de respuesta</TableHead>
                  <TableHead>Peso</TableHead>
                  <TableHead>Requerido</TableHead>
                  {canEdit && <TableHead>Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {requirements.map((requirement) => (
                  <Fragment key={requirement.id}>
                    <TableRow>
                      <TableCell>
                        {canEdit ? (
                          <Input
                            type="number"
                            step={1}
                            className="h-7 w-16"
                            value={orderDraft[requirement.id] ?? requirement.display_order}
                            onChange={(event) =>
                              setOrderDraft((prev) => ({
                                ...prev,
                                [requirement.id]: event.target.value,
                              }))
                            }
                            onBlur={() => handleOrderCommit(requirement)}
                            aria-label={`Orden de ${requirement.title}`}
                          />
                        ) : (
                          requirement.display_order
                        )}
                      </TableCell>
                      <TableCell>{requirement.category}</TableCell>
                      <TableCell>{requirement.title}</TableCell>
                      <TableCell>
                        <PriorityBadge priority={requirement.priority} />
                      </TableCell>
                      <TableCell>{translateResponseType(requirement.response_type)}</TableCell>
                      <TableCell>{requirement.weight}</TableCell>
                      <TableCell>{requirement.required ? 'Sí' : 'No'}</TableCell>
                      {canEdit && (
                        <TableCell>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setFormTarget({ mode: 'edit', requirement })}
                            >
                              Editar
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setPendingDeleteId(requirement.id)}
                            >
                              Eliminar
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                    {formTarget?.mode === 'edit' &&
                      formTarget.requirement.id === requirement.id && (
                        <TableRow>
                          <TableCell colSpan={canEdit ? 8 : 7}>
                            <RequirementForm
                              requirement={requirement}
                              defaultDimension={dimension}
                              nextDisplayOrder={requirement.display_order}
                              onSubmit={(payload) => handleUpdate(requirement.id, payload)}
                              onCancel={() => setFormTarget(null)}
                              isSubmitting={updateRequirement.isPending}
                              submitError={updateRequirement.error}
                            />
                          </TableCell>
                        </TableRow>
                      )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {!canEdit && (
        <p className="mt-4 text-sm text-muted-foreground">
          {isOwner
            ? 'Los requerimientos solo pueden editarse mientras la evaluación está en borrador.'
            : 'Vista de solo lectura de los requerimientos.'}
        </p>
      )}

      {renderDimension('functional', 'Funcional')}
      {renderDimension('technical', 'Técnico')}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Eliminar requerimiento"
        description="Esta acción no se puede deshacer. El requerimiento se quitará de la evaluación."
        confirmLabel="Eliminar"
        variant="destructive"
        isPending={deleteRequirement.isPending}
        onConfirm={() => {
          if (!pendingDeleteId) return
          deleteRequirement.mutate(
            { evaluationId: evaluation.id, requirementId: pendingDeleteId },
            { onSuccess: () => setPendingDeleteId(null) },
          )
        }}
      />
    </div>
  )
}
