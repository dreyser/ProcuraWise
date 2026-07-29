const DIMENSION_TARGET_POINTS: Record<'functional' | 'technical', number> = {
  functional: 40,
  technical: 20,
}

const DIMENSION_LABEL: Record<'functional' | 'technical', string> = {
  functional: 'Funcional',
  technical: 'Técnico',
}

interface WeightSummaryProps {
  dimension: 'functional' | 'technical'
  currentWeight: number
}

/** Client-side preview only - `start-collection` is still what authoritatively
 * enforces the 40/20 rule server-side (brief §6/§18). */
export function WeightSummary({ dimension, currentWeight }: WeightSummaryProps) {
  const target = DIMENSION_TARGET_POINTS[dimension]
  const rounded = Math.round(currentWeight * 100) / 100
  const diff = Math.round((rounded - target) * 100) / 100
  const isExact = Math.abs(diff) < 1e-6

  return (
    <p className={`text-sm ${isExact ? 'text-muted-foreground' : 'text-amber-700'}`} role="status">
      {DIMENSION_LABEL[dimension]}: {rounded} / {target} puntos
      {!isExact &&
        (diff > 0
          ? ` — excede el objetivo por ${diff}`
          : ` — faltan ${Math.abs(diff)} para el objetivo`)}
    </p>
  )
}
