import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { ErrorBanner } from '@/components/ErrorBanner'
import { roleHomePath } from '@/app/roleHomePath'

/** Route target of the OIDC redirect chain: backend's /auth/oidc/{provider}/callback
 * 302s here with `#pre_session_token=...&expires_in=...` in the URL fragment
 * (never a query string, so it never reaches server logs/browser history in
 * a request line). Cleared from the address bar immediately via
 * history.replaceState before anything else happens. */
export function AuthCallbackPage() {
  const { completeOidcCallback, status } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true

    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const preSessionToken = fragment.get('pre_session_token')
    window.history.replaceState(null, '', window.location.pathname)

    if (!preSessionToken) {
      setError('No se recibió una sesión válida del proveedor. Intenta de nuevo.')
      return
    }

    completeOidcCallback(preSessionToken).then((result) => {
      if (!result.ok) {
        setError(result.message ?? 'No se pudo completar el inicio de sesión.')
        return
      }
      // If there was more than one workspace, status is now
      // 'awaiting_workspace' - navigate there explicitly since this page
      // has no RequireAuth guard of its own to do it declaratively.
      if (status !== 'ready') {
        navigate('/auth/select-workspace', { replace: true })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (status === 'ready') {
      navigate(roleHomePath('evaluation_owner'), { replace: true })
    }
  }, [status, navigate])

  if (error) {
    return (
      <main className="mx-auto max-w-md p-8">
        <ErrorBanner message={error} />
        <a href="/login" className="mt-4 inline-block text-sm text-primary underline">
          Volver a intentar
        </a>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground" role="status">
        Completando inicio de sesión…
      </p>
    </main>
  )
}
