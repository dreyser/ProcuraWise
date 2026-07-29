import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListEvaluationsApiV1EvaluationsGetQueryKey,
  useCreateEvaluationApiV1EvaluationsPost,
  type EvaluationDetailResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { unwrapDataOrThrow } from '@/lib/http'

const schema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  description: z.string().trim().optional(),
})

type FormValues = z.infer<typeof schema>

export function EvaluationCreatePage() {
  const navigate = useNavigate()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', description: '' },
  })
  const queryClient = useQueryClient()
  const createEvaluation = useCreateEvaluationApiV1EvaluationsPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListEvaluationsApiV1EvaluationsGetQueryKey() })
      },
    },
  })

  const onSubmit = async (values: FormValues) => {
    try {
      const response = await createEvaluation.mutateAsync({
        data: { name: values.name, description: values.description ?? '' },
      })
      const evaluation = unwrapDataOrThrow<EvaluationDetailResponse>(response)
      navigate(`/evaluations/${evaluation.id}`, { replace: true })
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.fieldErrors) {
        for (const [field, message] of Object.entries(normalized.fieldErrors)) {
          if (field === 'name' || field === 'description') {
            setError(field, { message })
          }
        }
      }
    }
  }

  const submitError =
    createEvaluation.isError && !normalizeApiError(createEvaluation.error).fieldErrors
      ? normalizeApiError(createEvaluation.error).message
      : null

  return (
    <div className="max-w-lg">
      <h1 className="text-lg font-semibold text-foreground">Nueva evaluación</h1>
      <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {submitError && <ErrorBanner message={submitError} />}

        <div>
          <Label htmlFor="evaluation-name">Nombre</Label>
          <Input
            id="evaluation-name"
            {...register('name')}
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? 'evaluation-name-error' : undefined}
          />
          {errors.name && (
            <p id="evaluation-name-error" className="mt-1 text-sm text-destructive">
              {errors.name.message}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="evaluation-description">Descripción</Label>
          <Textarea
            id="evaluation-description"
            {...register('description')}
            aria-invalid={Boolean(errors.description)}
            aria-describedby={errors.description ? 'evaluation-description-error' : undefined}
          />
          {errors.description && (
            <p id="evaluation-description-error" className="mt-1 text-sm text-destructive">
              {errors.description.message}
            </p>
          )}
        </div>

        <Button type="submit" disabled={isSubmitting} className="self-start">
          {isSubmitting ? 'Creando…' : 'Crear evaluación'}
        </Button>
      </form>
    </div>
  )
}
