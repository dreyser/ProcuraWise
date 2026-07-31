/** `variant="info"` (Fase 12, plan §26/§32 Blocker 3): a non-destructive
 * counterpart used for messages that aren't errors but still need an
 * explicit, immediate notice - e.g. "your edit withdrew the pending
 * approval" - rather than a silently-updated status badge discovered later. */
export function ErrorBanner({
  message,
  variant = 'error',
  onDismiss,
}: {
  message: string
  variant?: 'error' | 'info'
  onDismiss?: () => void
}) {
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={
        variant === 'error'
          ? 'flex items-start justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
          : 'flex items-start justify-between gap-3 rounded-md border border-foreground/20 bg-muted px-4 py-3 text-sm text-foreground'
      }
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Cerrar"
          className="shrink-0 text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      )}
    </div>
  )
}
