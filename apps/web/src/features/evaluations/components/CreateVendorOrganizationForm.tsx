import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  useCreateVendorOrganizationApiV1VendorOrganizationsPost,
  type VendorOrganizationCreatedResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { unwrapDataOrThrow } from '@/lib/http'

const createVendorOrgSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  contact_email: z.string().trim().min(1, 'El correo es obligatorio').email('Correo inválido'),
  contact_display_name: z.string().trim().min(1, 'El nombre del contacto es obligatorio'),
})

type CreateVendorOrgFormValues = z.infer<typeof createVendorOrgSchema>

/**
 * Fase 15: closes the gap identified during planning - there was previously
 * no way at all for a comprador to onboard a vendor organization that
 * doesn't already exist in the catalog (only dev_seed.py could create one).
 * Creates the VendorOrganization and invites its primary contact in one
 * call; the invite link is shown to the caller exactly once (never logged,
 * never re-derivable - see identity/vendor_auth_schemas.py), so this form
 * hands it back via `onCreated` rather than swallowing it.
 */
export function CreateVendorOrganizationForm({
  onCreated,
}: {
  onCreated: (result: VendorOrganizationCreatedResponse) => void
}) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateVendorOrgFormValues>({ resolver: zodResolver(createVendorOrgSchema) })

  const createVendorOrganization = useCreateVendorOrganizationApiV1VendorOrganizationsPost()

  const onSubmit = async (values: CreateVendorOrgFormValues) => {
    setSubmitError(null)
    try {
      const response = await createVendorOrganization.mutateAsync({ data: values })
      reset()
      onCreated(unwrapDataOrThrow<VendorOrganizationCreatedResponse>(response))
    } catch (error) {
      setSubmitError(normalizeApiError(error).message)
    }
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
      {submitError && <ErrorBanner message={submitError} />}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="vendor-org-name">Nombre del proveedor</Label>
        <Input id="vendor-org-name" aria-invalid={Boolean(errors.name)} {...register('name')} />
        {errors.name && (
          <p role="alert" className="text-xs text-destructive">
            {errors.name.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="vendor-contact-email">Correo del contacto principal</Label>
        <Input
          id="vendor-contact-email"
          type="email"
          aria-invalid={Boolean(errors.contact_email)}
          {...register('contact_email')}
        />
        {errors.contact_email && (
          <p role="alert" className="text-xs text-destructive">
            {errors.contact_email.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="vendor-contact-name">Nombre del contacto principal</Label>
        <Input
          id="vendor-contact-name"
          aria-invalid={Boolean(errors.contact_display_name)}
          {...register('contact_display_name')}
        />
        {errors.contact_display_name && (
          <p role="alert" className="text-xs text-destructive">
            {errors.contact_display_name.message}
          </p>
        )}
      </div>

      <Button type="submit" disabled={isSubmitting} className="self-start">
        {isSubmitting ? 'Creando…' : 'Crear proveedor e invitar'}
      </Button>
    </form>
  )
}
