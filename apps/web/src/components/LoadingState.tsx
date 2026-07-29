export function LoadingState({ label = 'Cargando…' }: { label?: string }) {
  return (
    <p role="status" className="text-sm text-muted-foreground">
      {label}
    </p>
  )
}
