import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost,
  type EvaluationDetailResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { startCollectionPreconditionReasons } from '@/features/evaluations/lib/evaluationReadiness'

interface WizardStepReviewProps {
  evaluation: EvaluationDetailResponse
  onBack: () => void
  onStarted: () => void
}

/** Step 4. Reuses the exact start-collection confirmation copy already
 * established in `VendorsPage` - the wizard's last step is what actually
 * closes "creation" by moving the evaluation into `collecting_responses`. */
export function WizardStepReview({ evaluation, onBack, onStarted }: WizardStepReviewProps) {
  const queryClient = useQueryClient()
  const [confirmStart, setConfirmStart] = useState(false)

  const startCollection = useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(
          getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluation.id),
          response,
        )
        setConfirmStart(false)
        onStarted()
      },
    },
  })

  const reasons = startCollectionPreconditionReasons(evaluation)
  const canStart = reasons.length === 0
  const functionalCount = evaluation.requirements.filter((r) => r.dimension === 'functional').length
  const technicalCount = evaluation.requirements.filter((r) => r.dimension === 'technical').length

  return (
    <div>
      <dl className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-muted-foreground">Requerimientos funcionales</dt>
          <dd className="text-foreground">{functionalCount}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Requerimientos técnicos</dt>
          <dd className="text-foreground">{technicalCount}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Proveedores vinculados</dt>
          <dd className="text-foreground">{evaluation.linked_vendor_count} / 6</dd>
        </div>
      </dl>

      <div className="mt-8 flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onBack}>
          Atrás
        </Button>
        <Button type="button" disabled={!canStart} onClick={() => setConfirmStart(true)}>
          Iniciar recepción de propuestas
        </Button>
      </div>
      <DisabledActionHint reasons={canStart ? [] : reasons} />
      {startCollection.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(startCollection.error).message} />
        </div>
      )}

      <ConfirmDialog
        open={confirmStart}
        onOpenChange={setConfirmStart}
        title="Iniciar recepción de propuestas"
        description="Los requerimientos y proveedores quedarán en modo de solo lectura. Los proveedores vinculados podrán empezar a responder."
        confirmLabel="Iniciar recepción"
        isPending={startCollection.isPending}
        onConfirm={() => startCollection.mutate({ evaluationId: evaluation.id })}
      />
    </div>
  )
}
