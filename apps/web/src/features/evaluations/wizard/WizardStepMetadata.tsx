import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  getListEvaluationsApiV1EvaluationsGetQueryKey,
  useCreateEvaluationApiV1EvaluationsPost,
  useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch,
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

interface WizardStepMetadataProps {
  evaluation: EvaluationDetailResponse | undefined
  onCreated: (evaluation: EvaluationDetailResponse) => void
  onNext: () => void
}

/** Step 1. Absorbs the form logic that used to live in the now-removed
 * `EvaluationCreatePage` - same schema, same fields. Doubles as the "rename"
 * form when the user navigates back here after the evaluation already
 * exists (PATCH instead of POST). */
export function WizardStepMetadata({ evaluation, onCreated, onNext }: WizardStepMetadataProps) {
  const queryClient = useQueryClient()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: evaluation?.name ?? '', description: evaluation?.description ?? '' },
  })

  useEffect(() => {
    if (evaluation) {
      reset({ name: evaluation.name, description: evaluation.description })
    }
  }, [evaluation, reset])

  const createEvaluation = useCreateEvaluationApiV1EvaluationsPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListEvaluationsApiV1EvaluationsGetQueryKey(),
        })
      },
    },
  })
  const updateEvaluation = useUpdateEvaluationApiV1EvaluationsEvaluationIdPatch({
    mutation: {
      onSuccess: (response) => {
        if (!evaluation) return
        queryClient.setQueryData(
          getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
          response,
        )
      },
    },
  })

  const isSaving = createEvaluation.isPending || updateEvaluation.isPending
  const saveError = createEvaluation.isError
    ? createEvaluation.error
    : updateEvaluation.isError
      ? updateEvaluation.error
      : null

  const onSubmit = async (values: FormValues) => {
    try {
      if (!evaluation) {
        const response = await createEvaluation.mutateAsync({
          data: { name: values.name, description: values.description ?? '' },
        })
        onCreated(unwrapDataOrThrow<EvaluationDetailResponse>(response))
        return
      }
      if (isDirty) {
        await updateEvaluation.mutateAsync({
          evaluationId: evaluation.id,
          data: { name: values.name, description: values.description ?? '' },
        })
      }
      onNext()
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

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
      {saveError && <ErrorBanner message={normalizeApiError(saveError).message} />}

      <div>
        <Label htmlFor="wizard-evaluation-name">Nombre</Label>
        <Input
          id="wizard-evaluation-name"
          {...register('name')}
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errors.name ? 'wizard-evaluation-name-error' : undefined}
        />
        {errors.name && (
          <p
            id="wizard-evaluation-name-error"
            className="mt-1 text-sm text-destructive"
            role="alert"
          >
            {errors.name.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="wizard-evaluation-description">Descripción</Label>
        <Textarea
          id="wizard-evaluation-description"
          {...register('description')}
          aria-invalid={Boolean(errors.description)}
          aria-describedby={errors.description ? 'wizard-evaluation-description-error' : undefined}
        />
        {errors.description && (
          <p
            id="wizard-evaluation-description-error"
            className="mt-1 text-sm text-destructive"
            role="alert"
          >
            {errors.description.message}
          </p>
        )}
      </div>

      <Button type="submit" disabled={isSubmitting || isSaving} className="self-start">
        {isSubmitting || isSaving ? 'Guardando…' : evaluation ? 'Siguiente' : 'Crear y continuar'}
      </Button>
    </form>
  )
}
