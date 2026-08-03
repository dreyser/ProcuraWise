import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  getListQuestionsAsBuyerApiV1EvaluationsEvaluationIdQuestionsGetQueryKey,
  useListQuestionsAsBuyerApiV1EvaluationsEvaluationIdQuestionsGet,
  usePublishAnswerApiV1EvaluationsEvaluationIdQuestionsQuestionIdAnswerPut,
  type BuyerQuestionListResponse,
  type BuyerQuestionResponse,
  type PublishAnswerRequestVisibility,
} from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/auth/AuthContext'
import { ApiError, unwrapData } from '@/lib/http'
import { normalizeApiError } from '@/lib/errors'
import { StatusBadge } from '@/components/StatusBadge'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useQnaPolling } from '@/features/evaluations/hooks/useQnaPolling'

const VISIBILITY_LABEL: Record<string, string> = {
  private: 'Privada',
  published_anonymized: 'Publicada (anónima)',
}

// Mirrors procurawise.shared.roles - only the evaluation owner may prepare
// and publish an answer (spec §6.6); every other BUYER_READ_ROLES member
// can read the full board but the backend 403s their writes, so the answer
// form must never render as usable for them.
const OWNER_ONLY = ['evaluation_owner']

interface AnswerDraft {
  body: string
  visibility: PublishAnswerRequestVisibility
}

export function QnaPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const queryClient = useQueryClient()
  const isOwner = Boolean(actor?.role && OWNER_ONLY.includes(actor.role))

  const listQuery = useListQuestionsAsBuyerApiV1EvaluationsEvaluationIdQuestionsGet(evaluationId!)
  const questions = unwrapData<BuyerQuestionListResponse>(listQuery.data)?.items ?? []

  useQnaPolling(async () => {
    await listQuery.refetch()
  })

  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>({})
  const [savingId, setSavingId] = useState<string | null>(null)
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [conflictIds, setConflictIds] = useState<Set<string>>(new Set())

  const publishAnswer = usePublishAnswerApiV1EvaluationsEvaluationIdQuestionsQuestionIdAnswerPut()

  const draftFor = (question: BuyerQuestionResponse): AnswerDraft =>
    drafts[question.id] ?? {
      body: question.current_answer?.body ?? '',
      visibility: question.current_answer?.visibility ?? 'private',
    }

  const handleSubmit = async (question: BuyerQuestionResponse) => {
    const draft = draftFor(question)
    if (!draft.body.trim()) return
    setSavingId(question.id)
    try {
      await publishAnswer.mutateAsync({
        evaluationId: evaluationId!,
        questionId: question.id,
        data: {
          body: draft.body.trim(),
          visibility: draft.visibility,
          expected_version: question.version,
        },
      })
      await queryClient.invalidateQueries({
        queryKey:
          getListQuestionsAsBuyerApiV1EvaluationsEvaluationIdQuestionsGetQueryKey(evaluationId),
      })
      setRowErrors((prev) => {
        const next = { ...prev }
        delete next[question.id]
        return next
      })
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[question.id]
        return next
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflictIds((prev) => new Set(prev).add(question.id))
      } else {
        setRowErrors((prev) => ({ ...prev, [question.id]: normalizeApiError(error).message }))
      }
    } finally {
      setSavingId(null)
    }
  }

  const handleResolveConflict = async (questionId: string) => {
    await listQuery.refetch()
    setDrafts((prev) => {
      const next = { ...prev }
      delete next[questionId]
      return next
    })
    setConflictIds((prev) => {
      const next = new Set(prev)
      next.delete(questionId)
      return next
    })
  }

  if (listQuery.isLoading) {
    return <LoadingState label="Cargando preguntas…" />
  }
  if (listQuery.error) {
    return <ErrorBanner message={normalizeApiError(listQuery.error).message} />
  }

  const openQuestions = questions.filter((q) => q.status === 'open')
  const answeredQuestions = questions.filter((q) => q.status === 'answered')

  const renderQuestion = (question: BuyerQuestionResponse) => {
    const draft = draftFor(question)
    const hasConflict = conflictIds.has(question.id)

    return (
      <li key={question.id} className="rounded-md border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium text-foreground">{question.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Proveedor: {question.vendor_org_id} ·{' '}
              {question.scope === 'requirement' ? 'Ligada a requerimiento' : 'General'}
            </p>
          </div>
          <StatusBadge label={question.status === 'open' ? 'Sin responder' : 'Respondida'} />
        </div>

        {question.current_answer && (
          <div className="mt-3 rounded-md bg-muted p-3">
            <p className="text-sm text-foreground">{question.current_answer.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {VISIBILITY_LABEL[question.current_answer.visibility] ??
                question.current_answer.visibility}
            </p>
          </div>
        )}

        {isOwner && (
          <div className="mt-3">
            <Textarea
              value={draft.body}
              onChange={(event) =>
                setDrafts((prev) => ({
                  ...prev,
                  [question.id]: { ...draft, body: event.target.value },
                }))
              }
              placeholder="Escribe la respuesta…"
              disabled={hasConflict}
            />

            <fieldset className="mt-2">
              <legend className="sr-only">Visibilidad de la respuesta</legend>
              <div className="flex gap-4">
                {(['private', 'published_anonymized'] as const).map((option) => (
                  <label key={option} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="radio"
                      name={`visibility-${question.id}`}
                      value={option}
                      checked={draft.visibility === option}
                      disabled={hasConflict}
                      onChange={() =>
                        setDrafts((prev) => ({
                          ...prev,
                          [question.id]: { ...draft, visibility: option },
                        }))
                      }
                    />
                    {VISIBILITY_LABEL[option]}
                  </label>
                ))}
              </div>
            </fieldset>

            {rowErrors[question.id] && (
              <div className="mt-2">
                <ErrorBanner message={rowErrors[question.id]} />
              </div>
            )}

            {hasConflict && (
              <div className="mt-2 flex items-center gap-2">
                <ErrorBanner message="Los datos cambiaron desde que cargaste esta pregunta." />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => handleResolveConflict(question.id)}
                >
                  Recargar
                </Button>
              </div>
            )}

            {!hasConflict && (
              <Button
                type="button"
                size="sm"
                className="mt-3"
                disabled={!draft.body.trim() || savingId === question.id}
                onClick={() => handleSubmit(question)}
              >
                {savingId === question.id
                  ? 'Guardando…'
                  : question.current_answer
                    ? 'Republicar respuesta'
                    : 'Publicar respuesta'}
              </Button>
            )}
          </div>
        )}
      </li>
    )
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold text-foreground">Preguntas y respuestas</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Sin responder: {openQuestions.length} / {questions.length}
      </p>

      {!isOwner && (
        <p className="mt-2 text-sm text-muted-foreground">
          Tu rol puede revisar esta sección, pero no puede responder ni publicar.
        </p>
      )}

      {questions.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Sin preguntas"
            description="Todavía no hay preguntas de proveedores."
          />
        </div>
      ) : (
        <>
          {openQuestions.length > 0 && (
            <section className="mt-4">
              <h2 className="text-sm font-semibold text-foreground">Sin responder</h2>
              <ul className="mt-2 flex flex-col gap-3">{openQuestions.map(renderQuestion)}</ul>
            </section>
          )}
          {answeredQuestions.length > 0 && (
            <section className="mt-6">
              <h2 className="text-sm font-semibold text-foreground">Respondidas</h2>
              <ul className="mt-2 flex flex-col gap-3">{answeredQuestions.map(renderQuestion)}</ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}
