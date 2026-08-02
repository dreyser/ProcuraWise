import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useVendorAuth } from '@/vendor-auth/VendorAuthContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { roleHomePath } from '@/app/roleHomePath'

const acceptInvitationSchema = z
  .object({
    password: z.string().min(8, 'La contraseña debe tener al menos 8 caracteres'),
    confirmPassword: z.string().min(1, 'Confirma tu contraseña'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Las contraseñas no coinciden',
    path: ['confirmPassword'],
  })

type AcceptInvitationFormValues = z.infer<typeof acceptInvitationSchema>

export function AcceptInvitationPage() {
  const { acceptInvitation } = useVendorAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [submitError, setSubmitError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AcceptInvitationFormValues>({ resolver: zodResolver(acceptInvitationSchema) })

  if (!token) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-8">
        <h1 className="text-lg font-semibold text-foreground">Enlace de invitación inválido</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Este enlace no incluye un token de invitación. Pide al comprador que te reenvíe el enlace.
        </p>
        <Link className="mt-4 text-sm text-primary underline" to="/vendor/login">
          Ya tengo una cuenta, ir a iniciar sesión
        </Link>
      </main>
    )
  }

  const onSubmit = async (values: AcceptInvitationFormValues) => {
    setSubmitError(null)
    const result = await acceptInvitation(token, values.password)
    if (!result.ok) {
      setSubmitError(result.message ?? 'No se pudo completar el registro.')
      return
    }
    navigate(roleHomePath('vendor_contact'), { replace: true })
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-8">
      <h1 className="text-lg font-semibold text-foreground">Completa tu acceso</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Elige una contraseña para tu cuenta de proveedor en ProcuraWise.
      </p>

      {submitError && (
        <div className="mt-4">
          <ErrorBanner message={submitError} />
        </div>
      )}

      <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Contraseña</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'password-error' : undefined}
            {...register('password')}
          />
          {errors.password && (
            <p id="password-error" role="alert" className="text-xs text-destructive">
              {errors.password.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirmPassword">Confirma tu contraseña</Label>
          <Input
            id="confirmPassword"
            type="password"
            autoComplete="new-password"
            aria-invalid={Boolean(errors.confirmPassword)}
            aria-describedby={errors.confirmPassword ? 'confirm-password-error' : undefined}
            {...register('confirmPassword')}
          />
          {errors.confirmPassword && (
            <p id="confirm-password-error" role="alert" className="text-xs text-destructive">
              {errors.confirmPassword.message}
            </p>
          )}
        </div>

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Completando…' : 'Crear acceso'}
        </Button>
      </form>
    </main>
  )
}
