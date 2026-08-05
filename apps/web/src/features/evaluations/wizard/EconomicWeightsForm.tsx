import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useUpdateEconomicCriteriaWeightsApiV1EvaluationsEvaluationIdEconomicCriteriaWeightsPatch,
  type EvaluationDetailResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { translateEconomicCriterion } from '@/lib/enumLabels'

const COMMERCIAL_KEYS = [
  'payment_terms',
  'price_protection',
  'contractual_flexibility',
  'discounts_incentives',
  'billing_transparency',
] as const

const RISK_KEYS = [
  'variable_cost_exposure',
  'increases_indexation',
  'assumptions_exclusions',
  'fx_fiscal_regulatory',
  'exit_portability_lockin',
] as const

function sum(values: Record<string, number>): number {
  return Object.values(values).reduce((total, value) => total + value, 0)
}

interface EconomicWeightsFormProps {
  evaluation: EvaluationDetailResponse
}

/** Fase 20 (ADR 0009, plan §9 Pregunta Bloqueante #1) - the 5+5 criterion
 * keys are fixed (never authored here); only their numeric weights are
 * owner-editable, and only while `status === "draft"` (enforced again
 * server-side - this form is a convenience, not the authority). Each group
 * must sum to exactly 100. Frozen into EvaluationSnapshot at publish, same
 * moment as dimension_weights. */
export function EconomicWeightsForm({ evaluation }: EconomicWeightsFormProps) {
  const queryClient = useQueryClient()
  const [commercial, setCommercial] = useState<Record<string, number>>(
    evaluation.economic_criteria_weights.commercial,
  )
  const [risk, setRisk] = useState<Record<string, number>>(
    evaluation.economic_criteria_weights.risk,
  )

  useEffect(() => {
    setCommercial(evaluation.economic_criteria_weights.commercial)
    setRisk(evaluation.economic_criteria_weights.risk)
  }, [evaluation.economic_criteria_weights])

  const updateWeights =
    useUpdateEconomicCriteriaWeightsApiV1EvaluationsEvaluationIdEconomicCriteriaWeightsPatch({
      mutation: {
        onSuccess: (response) => {
          queryClient.setQueryData(
            getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
            response,
          )
        },
      },
    })

  const commercialSum = sum(commercial)
  const riskSum = sum(risk)
  const validSums = commercialSum === 100 && riskSum === 100

  const handleSave = () => {
    updateWeights.mutate({
      evaluationId: evaluation.id,
      data: { commercial, risk },
    })
  }

  return (
    <section className="mt-8 max-w-md">
      <h2 className="text-sm font-semibold text-foreground">Pesos de criterios económicos</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Los 10 criterios comerciales/de riesgo son fijos; solo su peso es editable aquí. Cada grupo
        debe sumar 100. Se congelan al publicar la evaluación.
      </p>

      <div className="mt-3">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">
          Condiciones comerciales ({commercialSum})
        </h3>
        <div className="mt-2 flex flex-col gap-2">
          {COMMERCIAL_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <Label htmlFor={`weight-${key}`} className="text-sm font-normal">
                {translateEconomicCriterion(key)}
              </Label>
              <Input
                id={`weight-${key}`}
                type="number"
                className="w-20"
                value={commercial[key]}
                onChange={(event) =>
                  setCommercial((prev) => ({ ...prev, [key]: Number(event.target.value) }))
                }
              />
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">
          Riesgo y predictibilidad ({riskSum})
        </h3>
        <div className="mt-2 flex flex-col gap-2">
          {RISK_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <Label htmlFor={`weight-${key}`} className="text-sm font-normal">
                {translateEconomicCriterion(key)}
              </Label>
              <Input
                id={`weight-${key}`}
                type="number"
                className="w-20"
                value={risk[key]}
                onChange={(event) =>
                  setRisk((prev) => ({ ...prev, [key]: Number(event.target.value) }))
                }
              />
            </div>
          ))}
        </div>
      </div>

      {!validSums && (
        <p className="mt-2 text-xs text-destructive">
          Cada grupo debe sumar exactamente 100 (comercial: {commercialSum}, riesgo: {riskSum}).
        </p>
      )}
      {updateWeights.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(updateWeights.error).message} />
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3"
        disabled={!validSums || updateWeights.isPending}
        onClick={handleSave}
      >
        {updateWeights.isPending ? 'Guardando…' : 'Guardar pesos económicos'}
      </Button>
    </section>
  )
}
