import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListTemplatesApiV1KnowledgeTemplatesGetQueryKey,
  useCreateTemplateApiV1KnowledgeTemplatesPost,
  useListTemplatesApiV1KnowledgeTemplatesGet,
  type KnowledgeTemplateDetailResponse,
  type KnowledgeTemplateListResponse,
} from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
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
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'

export function KnowledgeTemplatesPage() {
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data: response, isLoading, error } = useListTemplatesApiV1KnowledgeTemplatesGet()
  const templates = unwrapData<KnowledgeTemplateListResponse>(response)?.items ?? []

  const [isCreating, setIsCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const createTemplate = useCreateTemplateApiV1KnowledgeTemplatesPost({
    mutation: {
      onSuccess: (response) => {
        queryClient.invalidateQueries({
          queryKey: getListTemplatesApiV1KnowledgeTemplatesGetQueryKey(),
        })
        setIsCreating(false)
        setName('')
        setDescription('')
        const created = unwrapData<KnowledgeTemplateDetailResponse>(response)
        if (created) navigate(`/knowledge-templates/${created.id}`)
      },
    },
  })

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Biblioteca de requerimientos</h1>
        {isOwner && !isCreating && (
          <Button type="button" onClick={() => setIsCreating(true)}>
            Nueva plantilla
          </Button>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Guarda conjuntos de requerimientos reutilizables y aplícalos a una evaluación nueva.
      </p>

      {isCreating && (
        <form
          className="mt-4 flex max-w-lg flex-col gap-3 rounded-md border border-border p-4"
          onSubmit={(event) => {
            event.preventDefault()
            createTemplate.mutate({ data: { name, description } })
          }}
        >
          {createTemplate.isError && (
            <ErrorBanner message={normalizeApiError(createTemplate.error).message} />
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
            <Button type="submit" disabled={createTemplate.isPending || !name.trim()}>
              {createTemplate.isPending ? 'Guardando…' : 'Crear plantilla'}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={createTemplate.isPending}
              onClick={() => setIsCreating(false)}
            >
              Cancelar
            </Button>
          </div>
        </form>
      )}

      <div className="mt-4">
        {isLoading && <LoadingState label="Cargando plantillas…" />}
        {error && <ErrorBanner message={normalizeApiError(error).message} />}
        {!isLoading && templates.length === 0 && (
          <EmptyState
            title="Todavía no hay plantillas"
            description={
              isOwner
                ? 'Crea la primera plantilla para reutilizar requerimientos entre evaluaciones.'
                : 'El responsable de evaluación aún no ha creado ninguna plantilla.'
            }
          />
        )}
        {templates.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Descripción</TableHead>
                  <TableHead>Requerimientos</TableHead>
                  <TableHead>Última actualización</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {templates.map((template) => (
                  <TableRow key={template.id}>
                    <TableCell>
                      <Link
                        to={`/knowledge-templates/${template.id}`}
                        className="font-medium text-foreground underline-offset-2 hover:underline"
                      >
                        {template.name}
                      </Link>
                    </TableCell>
                    <TableCell>{template.description || '—'}</TableCell>
                    <TableCell>{template.item_count}</TableCell>
                    <TableCell>
                      {new Date(template.updated_at).toLocaleDateString('es-MX')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  )
}
