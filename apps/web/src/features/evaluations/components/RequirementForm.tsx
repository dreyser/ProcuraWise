import { useFieldArray, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { dimensionLabels, priorityLabels, responseTypeLabels } from '@/lib/enumLabels'
import type { RequirementResponse } from '@/api/client'

const CHOICE_TYPES = new Set(['single_choice', 'multi_choice'])

const schema = z
  .object({
    dimension: z.enum(['functional', 'technical']),
    category: z.string().trim().min(1, 'La categoría es obligatoria'),
    title: z.string().trim().min(1, 'El título es obligatorio'),
    description: z.string().trim().min(1, 'La descripción es obligatoria'),
    priority: z.enum(['mandatory', 'important', 'desirable']),
    response_type: z.enum([
      'compliant_status',
      'text',
      'single_choice',
      'multi_choice',
      'number',
      'percentage',
      'date',
      'url',
      'comment',
      'currency',
    ]),
    weight: z.coerce.number().min(0, 'El peso debe ser mayor o igual a 0'),
    required: z.boolean(),
    buyer_guidance: z.string().trim().optional(),
    display_order: z.coerce.number().int().min(1, 'El orden debe ser mayor o igual a 1'),
    options: z.array(
      z.object({ value: z.string().trim().min(1, 'La opción no puede estar vacía') }),
    ),
  })
  .superRefine((data, ctx) => {
    if (CHOICE_TYPES.has(data.response_type) && data.options.length === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['options'],
        message: 'Agrega al menos una opción para este tipo de respuesta',
      })
    }
  })

export type RequirementFormValues = z.infer<typeof schema>

export interface RequirementSubmitPayload {
  dimension: 'functional' | 'technical'
  category: string
  title: string
  description: string
  priority: 'mandatory' | 'important' | 'desirable'
  response_type: RequirementFormValues['response_type']
  weight: number
  required: boolean
  buyer_guidance?: string
  display_order: number
  options?: string[] | null
}

function toDefaultValues(
  requirement: RequirementResponse | undefined,
  defaultDimension: 'functional' | 'technical',
  nextDisplayOrder: number,
): RequirementFormValues {
  if (!requirement) {
    return {
      dimension: defaultDimension,
      category: '',
      title: '',
      description: '',
      priority: 'important',
      response_type: 'text',
      weight: 0,
      required: true,
      buyer_guidance: '',
      display_order: nextDisplayOrder,
      options: [],
    }
  }
  return {
    dimension: requirement.dimension,
    category: requirement.category,
    title: requirement.title,
    description: requirement.description,
    priority: requirement.priority,
    response_type: requirement.response_type,
    weight: requirement.weight,
    required: requirement.required,
    buyer_guidance: requirement.buyer_guidance ?? '',
    display_order: requirement.display_order,
    options: (requirement.options ?? []).map((value) => ({ value })),
  }
}

interface RequirementFormProps {
  requirement?: RequirementResponse
  defaultDimension: 'functional' | 'technical'
  nextDisplayOrder: number
  onSubmit: (payload: RequirementSubmitPayload) => Promise<void>
  onCancel: () => void
  isSubmitting: boolean
  submitError: unknown
}

export function RequirementForm({
  requirement,
  defaultDimension,
  nextDisplayOrder,
  onSubmit,
  onCancel,
  isSubmitting,
  submitError,
}: RequirementFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    control,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: toDefaultValues(requirement, defaultDimension, nextDisplayOrder),
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'options' })
  const responseType = watch('response_type')
  const isChoiceType = CHOICE_TYPES.has(responseType)

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      dimension: values.dimension,
      category: values.category,
      title: values.title,
      description: values.description,
      priority: values.priority,
      response_type: values.response_type,
      weight: values.weight,
      required: values.required,
      buyer_guidance: values.buyer_guidance || undefined,
      display_order: values.display_order,
      options: isChoiceType ? values.options.map((o) => o.value) : undefined,
    })
  })

  return (
    <form
      className="flex flex-col gap-4 rounded-md border border-border p-4"
      onSubmit={submit}
      noValidate
    >
      {Boolean(submitError) && <ErrorBanner message={normalizeApiError(submitError).message} />}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="req-dimension">Dimensión</Label>
          <select
            id="req-dimension"
            {...register('dimension')}
            className="mt-1 h-8 w-full rounded-lg border border-border bg-background px-2 text-sm"
          >
            {Object.entries(dimensionLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="req-priority">Prioridad</Label>
          <select
            id="req-priority"
            {...register('priority')}
            className="mt-1 h-8 w-full rounded-lg border border-border bg-background px-2 text-sm"
          >
            {Object.entries(priorityLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <Label htmlFor="req-category">Categoría</Label>
        <Input
          id="req-category"
          {...register('category')}
          aria-invalid={Boolean(errors.category)}
          aria-describedby={errors.category ? 'req-category-error' : undefined}
        />
        {errors.category && (
          <p id="req-category-error" className="mt-1 text-sm text-destructive" role="alert">
            {errors.category.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="req-title">Título</Label>
        <Input
          id="req-title"
          {...register('title')}
          aria-invalid={Boolean(errors.title)}
          aria-describedby={errors.title ? 'req-title-error' : undefined}
        />
        {errors.title && (
          <p id="req-title-error" className="mt-1 text-sm text-destructive" role="alert">
            {errors.title.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="req-description">Descripción</Label>
        <Textarea
          id="req-description"
          {...register('description')}
          aria-invalid={Boolean(errors.description)}
          aria-describedby={errors.description ? 'req-description-error' : undefined}
        />
        {errors.description && (
          <p id="req-description-error" className="mt-1 text-sm text-destructive" role="alert">
            {errors.description.message}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="req-buyer-guidance">Guía para el proveedor (opcional)</Label>
        <Textarea id="req-buyer-guidance" {...register('buyer_guidance')} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <Label htmlFor="req-response-type">Tipo de respuesta</Label>
          <select
            id="req-response-type"
            {...register('response_type')}
            className="mt-1 h-8 w-full rounded-lg border border-border bg-background px-2 text-sm"
          >
            {Object.entries(responseTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="req-weight">Peso</Label>
          <Input
            id="req-weight"
            type="number"
            step="0.1"
            {...register('weight')}
            aria-invalid={Boolean(errors.weight)}
            aria-describedby={errors.weight ? 'req-weight-error' : undefined}
          />
          {errors.weight && (
            <p id="req-weight-error" className="mt-1 text-sm text-destructive" role="alert">
              {errors.weight.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="req-display-order">Orden</Label>
          <Input
            id="req-display-order"
            type="number"
            step="1"
            {...register('display_order')}
            aria-invalid={Boolean(errors.display_order)}
            aria-describedby={errors.display_order ? 'req-display-order-error' : undefined}
          />
          {errors.display_order && (
            <p id="req-display-order-error" className="mt-1 text-sm text-destructive" role="alert">
              {errors.display_order.message}
            </p>
          )}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="checkbox" {...register('required')} className="size-4" />
        Respuesta requerida antes de enviar la propuesta
      </label>

      {isChoiceType && (
        <fieldset aria-describedby={errors.options ? 'req-options-error' : undefined}>
          <legend className="mb-1 text-sm font-medium">Opciones</legend>
          <div className="flex flex-col gap-2">
            {fields.map((field, index) => (
              <div key={field.id} className="flex items-center gap-2">
                <Input
                  {...register(`options.${index}.value` as const)}
                  aria-label={`Opción ${index + 1}`}
                />
                <Button type="button" variant="ghost" size="sm" onClick={() => remove(index)}>
                  Quitar
                </Button>
              </div>
            ))}
          </div>
          {errors.options && typeof errors.options.message === 'string' && (
            <p id="req-options-error" className="mt-1 text-sm text-destructive" role="alert">
              {errors.options.message}
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => append({ value: '' })}
          >
            Agregar opción
          </Button>
        </fieldset>
      )}

      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Guardando…' : 'Guardar requerimiento'}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancelar
        </Button>
      </div>
    </form>
  )
}
