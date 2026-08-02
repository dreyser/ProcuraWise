import { useState } from 'react'

/**
 * Fase 15: the invite link/token is returned exactly once by the backend
 * (never logged, never re-derivable - identity/vendor_auth_schemas.py) as a
 * deliberate substitute for real email sending (Fase 24). This is the only
 * place in the UI that ever sees the raw token - it must be copied and
 * relayed to the vendor contact through whatever channel the comprador
 * chooses.
 */
export function InviteLinkNotice({
  email,
  inviteUrl,
  onDismiss,
}: {
  email: string
  inviteUrl: string
  onDismiss: () => void
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="rounded-md border border-primary/30 bg-primary/5 p-4">
      <p className="text-sm font-medium text-foreground">Invitación creada para {email}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Este enlace solo se muestra una vez. Cópialo y envíaselo al proveedor por el medio que
        prefieras (todavía no hay envío de correo automático).
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <code className="break-all rounded bg-muted px-2 py-1 text-xs">{inviteUrl}</code>
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-border px-2 py-1 text-xs hover:bg-accent"
        >
          {copied ? 'Copiado' : 'Copiar enlace'}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md border border-border px-2 py-1 text-xs hover:bg-accent"
        >
          Cerrar
        </button>
      </div>
    </div>
  )
}
