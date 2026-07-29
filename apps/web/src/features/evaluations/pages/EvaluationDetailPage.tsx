import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch,
  type EvaluationDetailResponse,
} from '@/api/client'
import { ApiError, unwrapData, unwrapDataOrThrow } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { translateEvaluationStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'

const schema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  description: z.string().trim().optional(),
})

type FormValues = z.infer<typeof schema>

export function EvaluationDetailPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(data)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', description: '' },
  })

  useEffect(() => {
    if (evaluation) {
      reset({ name: evaluation.name, description: evaluation.description })
    }
  }, [evaluation, reset])

  const updateEvaluation = useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(
          getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
          response,
        )
        const updated = unwrapDataOrThrow<EvaluationDetailResponse>(response)
        reset({ name: updated.name, description: updated.description })
      },
    },
  })

  if (isLoading) return <LoadingState label="Cargando evaluación…" />
  if (error instanceof ApiError && error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (error) return <ErrorBanner message={normalizeApiError(error).message} />
  if (!evaluation) return null

  const canEdit = isOwner && evaluation.status === 'draft'

  const onSubmit = (values: FormValues) => {
    updateEvaluation.mutate({
      evaluationId: evaluation.id,
      data: { name: values.name, description: values.description ?? '' },
    })
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      <div className="mt-4">
        {canEdit ? (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            {updateEvaluation.isError && (
              <ErrorBanner message={normalizeApiError(updateEvaluation.error).message} />
            )}
            <div>
              <Label htmlFor="evaluation-name">Nombre</Label>
              <Input
                id="evaluation-name"
                {...register('name')}
                aria-invalid={Boolean(errors.name)}
              />
              {errors.name && (
                <p className="mt-1 text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="evaluation-description">Descripción</Label>
              <Textarea id="evaluation-description" {...register('description')} />
            </div>
            <Button
              type="submit"
              disabled={!isDirty || updateEvaluation.isPending}
              className="self-start"
            >
              {updateEvaluation.isPending ? 'Guardando…' : 'Guardar cambios'}
            </Button>
          </form>
        ) : (
          <div>
            <p className="text-sm text-muted-foreground">
              {evaluation.description || 'Sin descripción.'}
            </p>
            {!isOwner && (
              <p className="mt-2 text-sm text-muted-foreground">
                Solo el responsable de evaluación puede editar esta información.
              </p>
            )}
            {isOwner && evaluation.status !== 'draft' && (
              <p className="mt-2 text-sm text-muted-foreground">
                La información ya no es editable fuera del estado borrador.
              </p>
            )}
          </div>
        )}

        <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Requerimientos</dt>
            <dd className="text-foreground">{evaluation.requirements.length}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Proveedores vinculados</dt>
            <dd className="text-foreground">{evaluation.linked_vendor_count} / 6</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
