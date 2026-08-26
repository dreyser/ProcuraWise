import { Fragment, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetTemplateApiV1KnowledgeTemplatesTemplateIdGetQueryKey,
  getListTemplatesApiV1KnowledgeTemplatesGetQueryKey,
  useAddItemApiV1KnowledgeTemplatesTemplateIdItemsPost,
  useDeleteItemApiV1KnowledgeTemplatesTemplateIdItemsItemIdDelete,
  useDeleteTemplateApiV1KnowledgeTemplatesTemplateIdDelete,
  useGetTemplateApiV1KnowledgeTemplatesTemplateIdGet,
  useUpdateItemApiV1KnowledgeTemplatesTemplateIdItemsItemIdPatch,
  useUpdateTemplateApiV1KnowledgeTemplatesTemplateIdPatch,
  type KnowledgeTemplateDetailResponse,
  type RequirementResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { PriorityBadge } from '@/components/PriorityBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateResponseType } from '@/lib/enumLabels'
import { pointsToPercent } from '@/features/evaluations/lib/evaluationReadiness'
import { normalizeApiError } from '@/lib/errors'
import {
  RequirementForm,
  type RequirementSubmitPayload,
} from '@/features/evaluations/components/RequirementForm'

type Dimension = 'functional' | 'technical'
type FormTarget =
  { mode: 'create'; dimension: Dimension } | { mode: 'edit'; item: RequirementResponse }

export function KnowledgeTemplateDetailPage() {
  const { templateId } = useParams<{ templateId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading, error } = useGetTemplateApiV1KnowledgeTemplatesTemplateIdGet(templateId!)
  const template = unwrapData<KnowledgeTemplateDetailResponse>(data)

  const [isEditingMetadata, setIsEditingMetadata] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [formTarget, setFormTarget] = useState<FormTarget | null>(null)
  const [pendingDeleteItemId, setPendingDeleteItemId] = useState<string | null>(null)
  const [pendingDeleteTemplate, setPendingDeleteTemplate] = useState(false)

  const invalidateTemplate = () => {
    queryClient.invalidateQueries({
      queryKey: getGetTemplateApiV1KnowledgeTemplatesTemplateIdGetQueryKey(templateId),
    })
    // item_count on the summary list (and the ApplyTemplateButton picker
    // that reuses it) would otherwise go stale until the query's staleTime
    // elapses - every mutation here changes it, so keep both in sync.
    queryClient.invalidateQueries({
      queryKey: getListTemplatesApiV1KnowledgeTemplatesGetQueryKey(),
    })
  }

  const updateTemplate = useUpdateTemplateApiV1KnowledgeTemplatesTemplateIdPatch({
    mutation: {
      onSuccess: () => {
        invalidateTemplate()
        setIsEditingMetadata(false)
      },
    },
  })
  const addItem = useAddItemApiV1KnowledgeTemplatesTemplateIdItemsPost({
    mutation: { onSuccess: invalidateTemplate },
  })
  const updateItem = useUpdateItemApiV1KnowledgeTemplatesTemplateIdItemsItemIdPatch({
    mutation: { onSuccess: invalidateTemplate },
  })
  const deleteItem = useDeleteItemApiV1KnowledgeTemplatesTemplateIdItemsItemIdDelete({
    mutation: { onSuccess: invalidateTemplate },
  })
  const deleteTemplate = useDeleteTemplateApiV1KnowledgeTemplatesTemplateIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListTemplatesApiV1KnowledgeTemplatesGetQueryKey(),
        })
        navigate('/knowledge-templates', { replace: true })
      },
    },
  })

  if (isLoading) return <LoadingState label="Cargando plantilla…" />
  if (error instanceof ApiError && error.status === 404) {
    return <ErrorBanner message="Esta plantilla no está disponible." />
  }
  if (error) return <ErrorBanner message={normalizeApiError(error).message} />
  if (!template) return null

  const byDimension = (dimension: Dimension) =>
    template.items
      .filter((item) => item.dimension === dimension)
      .sort((a, b) => a.display_order - b.display_order)

  const handleCreate = async (payload: RequirementSubmitPayload) => {
    await addItem.mutateAsync({ templateId: template.id, data: payload })
    setFormTarget(null)
  }

  const handleUpdate = async (itemId: string, payload: RequirementSubmitPayload) => {
    await updateItem.mutateAsync({ templateId: template.id, itemId, data: payload })
    setFormTarget(null)
  }

  const renderDimension = (dimension: Dimension, title: string) => {
    const items = byDimension(dimension)
    return (
      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {isOwner && formTarget?.mode !== 'create' && (
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

        {formTarget?.mode === 'create' && formTarget.dimension === dimension && (
          <div className="mt-2">
            <RequirementForm
              defaultDimension={dimension}
              nextDisplayOrder={items.length + 1}
              onSubmit={handleCreate}
              onCancel={() => setFormTarget(null)}
              isSubmitting={addItem.isPending}
              submitError={addItem.error}
            />
          </div>
        )}

        {items.length === 0 && formTarget?.mode !== 'create' && (
          <div className="mt-2">
            <EmptyState title="Sin requerimientos en esta dimensión" />
          </div>
        )}

        {items.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Orden</TableHead>
                  <TableHead>Categoría</TableHead>
                  <TableHead>Título</TableHead>
                  <TableHead>Prioridad</TableHead>
                  <TableHead>Tipo de respuesta</TableHead>
                  <TableHead>Peso (%)</TableHead>
                  <TableHead>Requerido</TableHead>
                  {isOwner && <TableHead>Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <Fragment key={item.id}>
                    <TableRow>
                      <TableCell>{item.display_order}</TableCell>
                      <TableCell>{item.category}</TableCell>
                      <TableCell>{item.title}</TableCell>
                      <TableCell>
                        <PriorityBadge priority={item.priority} />
                      </TableCell>
                      <TableCell>{translateResponseType(item.response_type)}</TableCell>
                      <TableCell>
                        {Math.round(pointsToPercent(item.weight, item.dimension) * 10) / 10}%
                      </TableCell>
                      <TableCell>{item.required ? 'Sí' : 'No'}</TableCell>
                      {isOwner && (
                        <TableCell>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setFormTarget({ mode: 'edit', item })}
                            >
                              Editar
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setPendingDeleteItemId(item.id)}
                            >
                              Eliminar
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                    {formTarget?.mode === 'edit' && formTarget.item.id === item.id && (
                      <TableRow>
                        <TableCell colSpan={isOwner ? 8 : 7}>
                          <RequirementForm
                            requirement={item}
                            defaultDimension={dimension}
                            nextDisplayOrder={item.display_order}
                            onSubmit={(payload) => handleUpdate(item.id, payload)}
                            onCancel={() => setFormTarget(null)}
                            isSubmitting={updateItem.isPending}
                            submitError={updateItem.error}
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
      <div className="flex items-center justify-between">
        {isEditingMetadata ? (
          <form
            className="flex max-w-lg flex-1 flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              updateTemplate.mutate({ templateId: template.id, data: { name, description } })
            }}
          >
            {updateTemplate.isError && (
              <ErrorBanner message={normalizeApiError(updateTemplate.error).message} />
            )}
            <div>
              <Label htmlFor="template-name">Nombre</Label>
              <Input
                id="template-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="template-description">Descripción (opcional)</Label>
              <Textarea
                id="template-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={updateTemplate.isPending || !name.trim()}>
                {updateTemplate.isPending ? 'Guardando…' : 'Guardar'}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={updateTemplate.isPending}
                onClick={() => setIsEditingMetadata(false)}
              >
                Cancelar
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <h1 className="text-lg font-semibold text-foreground">{template.name}</h1>
            {template.description && (
              <p className="mt-1 text-sm text-muted-foreground">{template.description}</p>
            )}
          </div>
        )}

        {isOwner && !isEditingMetadata && (
          <div className="flex shrink-0 gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setName(template.name)
                setDescription(template.description)
                setIsEditingMetadata(true)
              }}
            >
              Editar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => setPendingDeleteTemplate(true)}
            >
              Eliminar plantilla
            </Button>
          </div>
        )}
      </div>

      {renderDimension('functional', 'Funcional')}
      {renderDimension('technical', 'Técnico')}

      <ConfirmDialog
        open={pendingDeleteItemId !== null}
        onOpenChange={(open) => !open && setPendingDeleteItemId(null)}
        title="Eliminar requerimiento"
        description="Esta acción no se puede deshacer. El requerimiento se quitará de la plantilla."
        confirmLabel="Eliminar"
        variant="destructive"
        isPending={deleteItem.isPending}
        onConfirm={() => {
          if (!pendingDeleteItemId) return
          deleteItem.mutate(
            { templateId: template.id, itemId: pendingDeleteItemId },
            { onSuccess: () => setPendingDeleteItemId(null) },
          )
        }}
      />

      <ConfirmDialog
        open={pendingDeleteTemplate}
        onOpenChange={setPendingDeleteTemplate}
        title="Eliminar plantilla"
        description="Esta acción no se puede deshacer. La plantilla se eliminará permanentemente."
        confirmLabel="Eliminar"
        variant="destructive"
        isPending={deleteTemplate.isPending}
        onConfirm={() => deleteTemplate.mutate({ templateId: template.id })}
      />
    </div>
  )
}
