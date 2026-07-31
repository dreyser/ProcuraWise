import { Fragment, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useAddRequirementApiV1EvaluationsEvaluationIdRequirementsPost,
  useDeleteRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdDelete,
  useUpdateRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdPatch,
  type EvaluationDetailResponse,
  type RequirementResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { EmptyState } from '@/components/EmptyState'
import { PriorityBadge } from '@/components/PriorityBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateResponseType } from '@/lib/enumLabels'
import { ApplyTemplateButton } from '@/features/evaluations/components/ApplyTemplateButton'
import {
  RequirementForm,
  type RequirementSubmitPayload,
} from '@/features/evaluations/components/RequirementForm'
import { WeightSummary } from '@/features/evaluations/components/WeightSummary'
import { hasCompleteWeights } from '@/features/evaluations/lib/evaluationReadiness'

type Dimension = 'functional' | 'technical'
type FormTarget =
  { mode: 'create'; dimension: Dimension } | { mode: 'edit'; requirement: RequirementResponse }

interface WizardStepRequirementsProps {
  evaluation: EvaluationDetailResponse
  onChanged: () => void
  onBack: () => void
  onNext: () => void
}

/** Step 2. Add-focused composition of the same building blocks
 * `RequirementsPage` uses (`RequirementForm`/`WeightSummary`) - full
 * reordering stays on the "Requerimientos" tab, reachable at any time; the
 * wizard doesn't fork that logic. */
export function WizardStepRequirements({
  evaluation,
  onChanged,
  onBack,
  onNext,
}: WizardStepRequirementsProps) {
  const queryClient = useQueryClient()
  const [formTarget, setFormTarget] = useState<FormTarget | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const invalidate = () => {
    onChanged()
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
    })
  }

  const addRequirement = useAddRequirementApiV1EvaluationsEvaluationIdRequirementsPost({
    mutation: { onSuccess: invalidate },
  })
  const updateRequirement =
    useUpdateRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdPatch({
      mutation: { onSuccess: invalidate },
    })
  const deleteRequirement =
    useDeleteRequirementApiV1EvaluationsEvaluationIdRequirementsRequirementIdDelete({
      mutation: { onSuccess: invalidate },
    })

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

  const renderDimension = (dimension: Dimension, title: string) => {
    const requirements = byDimension(dimension)
    return (
      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {formTarget?.mode !== 'create' && (
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
                  <TableHead>Categoría</TableHead>
                  <TableHead>Título</TableHead>
                  <TableHead>Prioridad</TableHead>
                  <TableHead>Tipo de respuesta</TableHead>
                  <TableHead>Peso</TableHead>
                  <TableHead>Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requirements.map((requirement) => (
                  <Fragment key={requirement.id}>
                    <TableRow>
                      <TableCell>{requirement.category}</TableCell>
                      <TableCell>{requirement.title}</TableCell>
                      <TableCell>
                        <PriorityBadge priority={requirement.priority} />
                      </TableCell>
                      <TableCell>{translateResponseType(requirement.response_type)}</TableCell>
                      <TableCell>{requirement.weight}</TableCell>
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
                    </TableRow>
                    {formTarget?.mode === 'edit' &&
                      formTarget.requirement.id === requirement.id && (
                        <TableRow>
                          <TableCell colSpan={6}>
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

  const ready = hasCompleteWeights(evaluation)

  return (
    <div>
      <ApplyTemplateButton evaluationId={evaluation.id} onApplied={invalidate} />

      {renderDimension('functional', 'Funcional')}
      {renderDimension('technical', 'Técnico')}

      <div className="mt-8 flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onBack}>
          Atrás
        </Button>
        <Button type="button" disabled={!ready} onClick={onNext}>
          Siguiente
        </Button>
      </div>
      <DisabledActionHint
        reasons={
          ready
            ? []
            : [
                'Los requerimientos funcionales deben sumar 40 puntos y los técnicos 20 puntos para continuar.',
              ]
        }
      />

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
