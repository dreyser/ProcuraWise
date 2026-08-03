import { useState } from 'react'
import { useListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGet } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { useQuestionActions } from '@/features/vendor-portal/hooks/useQuestionActions'
import type { VendorQuestionListResponse } from '@/api/client'

interface RequirementQuestionThreadProps {
  proposalId: string
  requirementId: string
  disabled: boolean
}

const VISIBILITY_LABEL: Record<string, string> = {
  private: 'Privada',
  published_anonymized: 'Publicada (anónima)',
}

/** Questions tied to this specific requirement (brief §11.1) - a sibling of
 * RequirementEvidenceUpload, same compact inline placement. Fetches its own
 * "own questions" list - React Query dedupes against ProposalQnaPanel's
 * identical query. */
export function RequirementQuestionThread({
  proposalId,
  requirementId,
  disabled,
}: RequirementQuestionThreadProps) {
  const [draft, setDraft] = useState('')
  const actions = useQuestionActions(proposalId)

  const ownQuery = useListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGet(proposalId)
  const questions = (unwrapData<VendorQuestionListResponse>(ownQuery.data)?.items ?? []).filter(
    (q) => q.requirement_id === requirementId,
  )

  const handleSubmit = () => {
    if (!draft.trim()) return
    actions.create('requirement', draft.trim(), requirementId)
    setDraft('')
  }

  return (
    <div className="mt-3 rounded-md border border-dashed border-border p-3">
      <p className="text-xs font-medium text-muted-foreground">
        Preguntas sobre este requerimiento
      </p>

      {actions.createError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(actions.createError).message} />
        </div>
      )}
      {actions.withdrawError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(actions.withdrawError).message} />
        </div>
      )}

      {questions.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">Sin preguntas todavía.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {questions.map((question) => (
            <li key={question.id} className="rounded-md border border-border p-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium text-foreground">{question.body}</p>
                <div className="flex items-center gap-2">
                  <StatusBadge
                    label={question.status === 'open' ? 'Sin responder' : 'Respondida'}
                  />
                  {!disabled && question.status === 'open' && (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      disabled={actions.isWithdrawing}
                      onClick={() => actions.withdraw(question.id)}
                    >
                      Retirar
                    </Button>
                  )}
                </div>
              </div>
              {question.current_answer && (
                <div className="mt-2 rounded-md bg-muted p-2">
                  <p className="text-foreground">{question.current_answer.body}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {VISIBILITY_LABEL[question.current_answer.visibility] ??
                      question.current_answer.visibility}
                  </p>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!disabled && (
        <div className="mt-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Pregunta sobre este requerimiento…"
            disabled={actions.isCreating}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-2"
            disabled={actions.isCreating || !draft.trim()}
            onClick={handleSubmit}
          >
            {actions.isCreating ? 'Enviando…' : 'Preguntar'}
          </Button>
        </div>
      )}
    </div>
  )
}
