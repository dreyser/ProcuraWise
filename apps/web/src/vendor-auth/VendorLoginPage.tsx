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
import { isNextPathAllowedForRole, roleHomePath } from '@/app/roleHomePath'

const loginSchema = z.object({
  email: z.string().trim().min(1, 'El correo es obligatorio').email('Correo inválido'),
  password: z.string().min(1, 'La contraseña es obligatoria'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function VendorLoginPage() {
  const { loginWithPassword } = useVendorAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [submitError, setSubmitError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  const onSubmit = async (values: LoginFormValues) => {
    setSubmitError(null)
    const result = await loginWithPassword(values.email, values.password)
    if (!result.ok) {
      setSubmitError(result.message ?? 'No se pudo iniciar sesión.')
      return
    }
    const next = searchParams.get('next')
    const destination =
      next && isNextPathAllowedForRole(next, 'vendor_contact')
        ? next
        : roleHomePath('vendor_contact')
    navigate(destination, { replace: true })
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-8">
      <h1 className="text-lg font-semibold text-foreground">Acceso de proveedor</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Ingresa con el correo y contraseña que configuraste al aceptar tu invitación.
      </p>

      {submitError && (
        <div className="mt-4">
          <ErrorBanner message={submitError} />
        </div>
      )}

      <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Correo</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? 'email-error' : undefined}
            {...register('email')}
          />
          {errors.email && (
            <p id="email-error" role="alert" className="text-xs text-destructive">
              {errors.email.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Contraseña</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
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

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Entrando…' : 'Entrar'}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        ¿Eres comprador?{' '}
        <Link to="/login" className="text-primary underline">
          Ingresa a tu cuenta
        </Link>
      </p>
    </main>
  )
}
