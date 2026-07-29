export function UnauthorizedPage() {
  return (
    <div>
      <h1 className="text-lg font-semibold text-foreground">No tienes acceso a esta sección</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Tu rol actual no incluye esta pantalla. Cambia de actor si necesitas otra vista.
      </p>
    </div>
  )
}
