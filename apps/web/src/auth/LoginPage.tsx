import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
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

export function LoginPage() {
  const { loginWithPassword, beginOidcLogin } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [noBuyerAccess, setNoBuyerAccess] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  const onSubmit = async (values: LoginFormValues) => {
    setSubmitError(null)
    setNoBuyerAccess(false)
    const result = await loginWithPassword(values.email, values.password)
    if (!result.ok) {
      setSubmitError(result.message ?? 'No se pudo iniciar sesión.')
      setNoBuyerAccess(result.noBuyerAccess ?? false)
      return
    }
    // Fase 25: result.role is only set once a single Membership actually
    // resolved (AuthContext.switchTenant) - falls back to the generic buyer
    // home (a safe default, never wrong for the roles that share it) when
    // login instead lands on awaiting_workspace, which AppRouter's
    // RequireAuth redirects to /auth/select-workspace on its own regardless
    // of what this navigate() below targets.
    const role = result.role ?? 'evaluation_owner'
    const next = searchParams.get('next')
    if (next && isNextPathAllowedForRole(next, role)) {
      navigate(next, { replace: true })
      return
    }
    navigate(roleHomePath(role), { replace: true })
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-8">
      <h1 className="text-lg font-semibold text-foreground">Iniciar sesión</h1>
      <p className="mt-1 text-sm text-muted-foreground">Accede a tu cuenta de ProcuraWise.</p>

      {submitError && (
        <div className="mt-4">
          <ErrorBanner message={submitError} />
          {noBuyerAccess && (
            <Link to="/vendor/login" className="mt-2 block text-sm text-primary underline">
              Ir al portal de proveedores
            </Link>
          )}
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

      <div className="mt-6 flex flex-col gap-2 border-t border-border pt-6">
        <Button type="button" variant="outline" onClick={() => beginOidcLogin('microsoft')}>
          Continuar con Microsoft
        </Button>
        <Button type="button" variant="outline" onClick={() => beginOidcLogin('google')}>
          Continuar con Google
        </Button>
      </div>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        ¿Eres proveedor?{' '}
        <Link to="/vendor/login" className="text-primary underline">
          Ingresa al portal de proveedores
        </Link>
      </p>
    </main>
  )
}
