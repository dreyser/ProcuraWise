/** Bloque 1 stub - replaced with the real screen in its corresponding block. */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Esta pantalla se implementa en un bloque posterior de VS-2C.
      </p>
    </div>
  )
}
