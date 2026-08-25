import {
  DIMENSION_WEIGHT_TARGETS,
  pointsToPercent,
} from '@/features/evaluations/lib/evaluationReadiness'

const DIMENSION_LABEL: Record<'functional' | 'technical', string> = {
  functional: 'Funcional',
  technical: 'Técnico',
}

interface WeightSummaryProps {
  dimension: 'functional' | 'technical'
  currentWeight: number
}

/** Client-side preview only - `start-collection` is still what authoritatively
 * enforces the 40/20-point rule server-side (brief §6/§18, evaluations/
 * models.py's DIMENSION_MAX_POINTS - unchanged, no migration). UAT-02 (R4):
 * displayed in percent of that dimension's budget, since "this weighs 25%
 * of the functional score" is the mental model an owner actually reasons
 * in - the exactness check itself still happens in points (matching the
 * backend's own tolerance) via DIMENSION_WEIGHT_TARGETS, only the numbers
 * shown are converted. */
export function WeightSummary({ dimension, currentWeight }: WeightSummaryProps) {
  const target = DIMENSION_WEIGHT_TARGETS[dimension]
  const diffPoints = Math.round((currentWeight - target) * 100) / 100
  const isExact = Math.abs(diffPoints) < 1e-6
  const currentPercent = Math.round(pointsToPercent(currentWeight, dimension) * 10) / 10
  const diffPercent = Math.round(pointsToPercent(Math.abs(diffPoints), dimension) * 10) / 10

  return (
    <p className={`text-sm ${isExact ? 'text-muted-foreground' : 'text-amber-700'}`} role="status">
      {DIMENSION_LABEL[dimension]}: {currentPercent}% / 100%
      {!isExact &&
        (diffPoints > 0
          ? ` — excede el objetivo por ${diffPercent}%`
          : ` — faltan ${diffPercent}% para el objetivo`)}
    </p>
  )
}
