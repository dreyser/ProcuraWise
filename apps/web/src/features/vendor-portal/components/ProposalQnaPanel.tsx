import { useState } from 'react'
import {
  useListPublishedQuestionsApiV1VendorPortalProposalsProposalIdQuestionsPublishedGet,
  useListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGet,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { useQuestionActions } from '@/features/vendor-portal/hooks/useQuestionActions'
import type {
  PublicQuestionListResponse,
  VendorQuestionListResponse,
  VendorQuestionResponse,
} from '@/api/client'

interface ProposalQnaPanelProps {
  proposalId: string
  disabled: boolean
}

const VISIBILITY_LABEL: Record<string, string> = {
  private: 'Privada',
  published_anonymized: 'Publicada (anónima)',
}

function OwnQuestionCard({
  question,
  disabled,
  onWithdraw,
  withdrawing,
}: {
  question: VendorQuestionResponse
  disabled: boolean
  onWithdraw: () => void
  withdrawing: boolean
}) {
  return (
    <li className="rounded-md border border-border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-foreground">{question.body}</p>
        <div className="flex items-center gap-2">
          <StatusBadge label={question.status === 'open' ? 'Sin responder' : 'Respondida'} />
          {!disabled && question.status === 'open' && (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={withdrawing}
              onClick={onWithdraw}
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
  )
}

/** General, proposal-level questions (requirement_id=null) plus the read-only
 * board of other vendors' published_anonymized questions on the same
 * evaluation - brief §11.1: a Question's scope ("requirement" vs "general")
 * is a property of the vendor's own question, not a separate broadcast
 * mechanism (see plan §6.A/§7 - no unprompted buyer announcement exists in
 * this phase). Fetches its own lists - React Query dedupes against
 * RequirementQuestionThread's identical "own" query. */
export function ProposalQnaPanel({ proposalId, disabled }: ProposalQnaPanelProps) {
  const [draft, setDraft] = useState('')
  const actions = useQuestionActions(proposalId)

  const ownQuery = useListQuestionsApiV1VendorPortalProposalsProposalIdQuestionsGet(proposalId)
  const ownQuestions = (unwrapData<VendorQuestionListResponse>(ownQuery.data)?.items ?? []).filter(
    (q) => q.scope === 'general',
  )

  const publishedQuery =
    useListPublishedQuestionsApiV1VendorPortalProposalsProposalIdQuestionsPublishedGet(proposalId)
  const publishedQuestions =
    unwrapData<PublicQuestionListResponse>(publishedQuery.data)?.items ?? []

  const handleSubmit = () => {
    if (!draft.trim()) return
    actions.create('general', draft.trim())
    setDraft('')
  }

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="rounded-md border border-border p-4">
        <h2 className="text-sm font-semibold text-foreground">Preguntas generales</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Dudas sobre la propuesta que no están ligadas a un requerimiento específico.
        </p>

        {actions.createError && (
          <div className="mt-3">
            <ErrorBanner message={normalizeApiError(actions.createError).message} />
          </div>
        )}
        {actions.withdrawError && (
          <div className="mt-3">
            <ErrorBanner message={normalizeApiError(actions.withdrawError).message} />
          </div>
        )}

        <div className="mt-4">
          {ownQuery.isLoading ? (
            <LoadingState label="Cargando preguntas…" />
          ) : ownQuery.error ? (
            <ErrorBanner message={normalizeApiError(ownQuery.error).message} />
          ) : ownQuestions.length === 0 ? (
            <EmptyState
              title="Sin preguntas"
              description="Aún no has hecho ninguna pregunta general."
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {ownQuestions.map((question) => (
                <OwnQuestionCard
                  key={question.id}
                  question={question}
                  disabled={disabled}
                  withdrawing={actions.isWithdrawing}
                  onWithdraw={() => actions.withdraw(question.id)}
                />
              ))}
            </ul>
          )}
        </div>

        {!disabled && (
          <div className="mt-4">
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Escribe tu pregunta…"
              disabled={actions.isCreating}
            />
            <Button
              type="button"
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

      <div className="rounded-md border border-border p-4">
        <h2 className="text-sm font-semibold text-foreground">
          Preguntas públicas de otros proveedores
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Respuestas que el comprador publicó de forma anónima - nunca revelan qué proveedor
          preguntó.
        </p>
        <div className="mt-4">
          {publishedQuery.isLoading ? (
            <LoadingState label="Cargando…" />
          ) : publishedQuery.error ? (
            <ErrorBanner message={normalizeApiError(publishedQuery.error).message} />
          ) : publishedQuestions.length === 0 ? (
            <EmptyState
              title="Sin preguntas públicas"
              description="Todavía no hay respuestas publicadas de otros proveedores."
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {publishedQuestions.map((question) => (
                <li key={question.id} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium text-foreground">{question.body}</p>
                  {question.current_answer && (
                    <p className="mt-2 rounded-md bg-muted p-2 text-foreground">
                      {question.current_answer.body}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
